import importlib.machinery
import importlib.util
import shutil
import subprocess
import sys
import tempfile
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


def run(root, name, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts" / name), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )


def load_build(root):
    """Import a temp copy's scripts/build as a module so tests can swap
    GENERATORS and ROOT freely."""
    loader = importlib.machinery.SourceFileLoader(
        "bt_build_under_test", str(root / "scripts" / "build")
    )
    spec = importlib.util.spec_from_loader("bt_build_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class BumpVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)

    def test_bad_args_exit_2_without_writing(self):
        version_file = self.root / "VERSION"
        before = version_file.read_text()
        for bad in ("1.2", "v1.2.3", "latest"):
            with self.subTest(version=bad):
                proc = run(self.root, "bump-version", bad)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("bad version", proc.stderr)
                self.assertEqual(version_file.read_text(), before)
        proc = run(self.root, "build", "--bogus")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("Usage", proc.stderr)

    def test_bump_writes_version_and_reruns_build(self):
        proc = run(self.root, "bump-version", "1.2.3")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), "1.2.3\n")
        # Proof the build subprocess ran: only build prints this line.
        self.assertIn("nothing to build", proc.stdout)

    def test_check_fails_when_version_not_semver(self):
        (self.root / "VERSION").write_text("not-semver\n")
        proc = run(self.root, "bump-version", "--check")
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("semver", proc.stderr)

    def test_bump_restores_version_when_build_fails(self):
        (self.root / "scripts" / "build").write_text(
            "import sys\n\nGENERATORS = []\n\n"
            "def expected(root):\n    return {}\n\n"
            'if __name__ == "__main__":\n    sys.exit(1)\n'
        )
        (self.root / "VERSION").write_text("0.1.0\n")
        proc = run(self.root, "bump-version", "1.2.3")
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), "0.1.0\n")


class BuildManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        self.build = load_build(self.root)

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
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_no_generators_writes_no_manifest(self):
        self.build.GENERATORS = []
        self.assertEqual(self.build.main([]), 0)
        self.assertFalse((self.root / ".generated-files").exists())
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_check_fails_on_drift_and_missing_manifest(self):
        self.build.GENERATORS = [lambda root: {"g.txt": "v1"}]
        self.build.main([])
        (self.root / "g.txt").write_text("tampered")
        self.assertEqual(self.build.main(["--check"]), 1)
        self.build.main([])
        (self.root / ".generated-files").unlink()
        self.assertEqual(self.build.main(["--check"]), 1)


if __name__ == "__main__":
    unittest.main()
