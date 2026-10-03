import contextlib
import importlib.machinery
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def make_repo(tmp):
    """A throwaway repo root: scripts/, VERSION and kit.config.json copied
    so script tests never run against the real working tree."""
    root = Path(tmp)
    shutil.copytree(SCRIPTS, root / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("VERSION", "kit.config.json"):
        shutil.copy2(REPO / name, root / name)
    return root


def load_script(root, name, mod_name):
    """Import a temp copy's script as a module so tests can call
    main(argv) in-process and swap module globals freely."""
    loader = importlib.machinery.SourceFileLoader(
        mod_name, str(root / "scripts" / name)
    )
    spec = importlib.util.spec_from_loader(mod_name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def call(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mod.main(argv)
    return types.SimpleNamespace(
        returncode=code, stdout=out.getvalue(), stderr=err.getvalue()
    )


class FakeRun:
    """Stands in for subprocess.run so bump tests never spawn a process."""

    def __init__(self, rc):
        self.rc = rc
        self.calls = []

    def __call__(self, argv, cwd=None, **_kw):
        self.calls.append(argv)
        return types.SimpleNamespace(returncode=self.rc)


class BumpVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        self.bump = load_script(self.root, "bump-version", "bt_bump_under_test")

    def stub_build(self, rc):
        fake = FakeRun(rc)
        real = self.bump.subprocess
        self.bump.subprocess = types.SimpleNamespace(run=fake)
        self.addCleanup(setattr, self.bump, "subprocess", real)
        return fake

    def test_bad_args_exit_2_without_writing(self):
        version_file = self.root / "VERSION"
        before = version_file.read_text()
        for bad in ("1.2", "v1.2.3", "latest", "1.2.3-rc.1", "1.2.3+build"):
            with self.subTest(version=bad):
                proc = call(self.bump, [bad])
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("bad version", proc.stderr)
                self.assertEqual(version_file.read_text(), before)
        proc = call(self.bump, ["--bogus"])
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("bad version", proc.stderr)
        proc = call(self.bump, ["1.2.3", "extra"])
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("Usage", proc.stderr)

    def test_bump_writes_version_and_reruns_build(self):
        fake = self.stub_build(0)
        proc = call(self.bump, ["1.2.3"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), "1.2.3\n")
        self.assertEqual(
            fake.calls,
            [[sys.executable, str((self.root / "scripts" / "build").resolve())]],
        )

    def test_check_fails_when_version_not_semver(self):
        (self.root / "VERSION").write_text("not-semver\n")
        proc = call(self.bump, ["--check"])
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("semver", proc.stderr)
        (self.root / "VERSION").write_text("1.2.3-rc.1\n")
        proc = call(self.bump, ["--check"])
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("semver", proc.stderr)

    def test_check_passes_on_clean_tree(self):
        self.assertEqual(call(self.bump, ["--check"]).returncode, 0)

    def test_bump_restores_version_when_build_fails(self):
        self.stub_build(1)
        (self.root / "VERSION").write_text("0.1.0\n")
        proc = call(self.bump, ["1.2.3"])
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), "0.1.0\n")
        self.assertIn("0.1.0", proc.stderr)

    def test_bump_removes_version_when_build_fails_without_prior(self):
        self.stub_build(1)
        version_file = self.root / "VERSION"
        version_file.unlink()
        proc = call(self.bump, ["1.2.3"])
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(version_file.exists())
        self.assertIn("VERSION", proc.stderr)

    def test_cli_smoke(self):
        proc = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "bump-version"), "--check"],
            cwd=self.root, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class BuildManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        self.build = load_script(self.root, "build", "bt_build_under_test")

    def test_build_writes_manifest_and_check_catches_orphans(self):
        self.build.GENERATORS = [lambda root: {"gen/out.txt": "v1\n"}]
        self.assertEqual(self.build.main([]), 0)
        self.assertEqual((self.root / "gen" / "out.txt").read_text(), "v1\n")
        manifest = self.root / ".generated-files"
        self.assertTrue(manifest.is_file())
        self.assertEqual(manifest.read_text(), "gen/out.txt\n")
        self.assertEqual(self.build.main(["--check"]), 0)

        # A path dropped from the generators becomes an orphan.
        self.build.GENERATORS = [lambda root: {"gen/other.txt": "v2\n"}]
        self.assertEqual(self.build.main(["--check"]), 1)
        self.assertEqual(self.build.main([]), 0)
        self.assertFalse((self.root / "gen" / "out.txt").exists())
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_no_generators_removes_stale_manifest_and_orphans(self):
        self.build.GENERATORS = [lambda root: {"gen/out.txt": "v1\n"}]
        self.build.main([])
        self.assertTrue((self.root / ".generated-files").is_file())
        self.assertTrue((self.root / "gen" / "out.txt").is_file())
        self.build.GENERATORS = []
        self.assertEqual(self.build.main([]), 0)
        self.assertFalse((self.root / ".generated-files").exists())
        self.assertFalse((self.root / "gen" / "out.txt").exists())
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_check_fails_on_drift_and_missing_manifest(self):
        self.build.GENERATORS = [lambda root: {"g.txt": "v1"}]
        self.build.main([])
        (self.root / "g.txt").write_text("tampered")
        self.assertEqual(self.build.main(["--check"]), 1)
        self.build.main([])
        (self.root / ".generated-files").unlink()
        self.assertEqual(self.build.main(["--check"]), 1)

    def test_cli_smoke(self):
        proc = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "build"), "--check"],
            cwd=self.root, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
