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
    shutil.copytree(
        SCRIPTS, root / "scripts", ignore=shutil.ignore_patterns("__pycache__")
    )
    for name in ("VERSION", "kit.config.json", "CHANGELOG.md"):
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


def _raise(exc):
    raise exc


class BumpVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        self.bump = load_script(self.root, "bump-version", "bt_bump_under_test")

    def stub_build_outputs(self, files=None, exc=None):
        """Swap the build-module loader so bump sees canned outputs (or
        a generator failure) without a subprocess."""
        fake = types.SimpleNamespace(
            expected=lambda root: files if exc is None else _raise(exc)
        )
        real = self.bump._build_module
        self.bump._build_module = lambda: fake
        self.addCleanup(setattr, self.bump, "_build_module", real)

    def test_bad_args_exit_2_without_writing(self):
        version_file = self.root / "VERSION"
        before = version_file.read_text()
        for bad in (
            "1.2", "v1.2.3", "latest", "1.2.3-rc.1", "1.2.3+build",
            "01.2.3", "1.02.3", "1.2.3 ", "1.2.3\n", "١.٢.٣",
        ):
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

    def test_bump_writes_version_and_build_outputs(self):
        self.stub_build_outputs({"gen/out.txt": "v1\n"})
        proc = call(self.bump, ["1.2.3"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), "1.2.3\n")
        self.assertEqual((self.root / "gen" / "out.txt").read_text(), "v1\n")

    def test_bump_computes_outputs_before_any_write(self):
        # A generator failure leaves VERSION and the tree untouched.
        version_file = self.root / "VERSION"
        before = version_file.read_text()
        self.stub_build_outputs(exc=ValueError("two generators produce g.txt"))
        proc = call(self.bump, ["1.2.3"])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(version_file.read_text(), before)

    def test_bump_restores_touched_files_on_write_failure(self):
        # 'zz' exists as a file, so writing zz/x.txt fails mid-way after
        # a.txt and VERSION were already written: every touched file must
        # be restored (old bytes back, new files removed).
        (self.root / "a.txt").write_text("old a\n")
        (self.root / "zz").write_text("not a dir\n")
        self.stub_build_outputs({"a.txt": "new a\n", "b.txt": "new b\n",
                                 "zz/x.txt": "x\n"})
        proc = call(self.bump, ["1.2.3"])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), "0.1.0\n")
        self.assertEqual((self.root / "a.txt").read_text(), "old a\n")
        self.assertFalse((self.root / "b.txt").exists())

    def test_bump_restores_missing_version_on_write_failure(self):
        (self.root / "VERSION").unlink()
        (self.root / "zz").write_text("not a dir\n")
        self.stub_build_outputs({"zz/x.txt": "x\n"})
        proc = call(self.bump, ["1.2.3"])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse((self.root / "VERSION").exists())

    def test_check_fails_when_version_not_semver(self):
        (self.root / "VERSION").write_text("not-semver\n")
        proc = call(self.bump, ["--check"])
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("semver", proc.stderr)
        (self.root / "VERSION").write_text("1.2.3-rc.1\n")
        proc = call(self.bump, ["--check"])
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("semver", proc.stderr)
        for bad in ("1.02.3", "١.٢.٣"):
            (self.root / "VERSION").write_text(bad + "\n")
            proc = call(self.bump, ["--check"])
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("semver", proc.stderr)

    def test_check_passes_on_clean_tree(self):
        self.assertEqual(call(self.bump, ["--check"]).returncode, 0)

    def test_cli_smoke(self):
        proc = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "bump-version"), "--check"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_bump_then_verify_still_passes(self):
        for name, argv in (
            ("bump-version", ["0.2.0"]),
            ("verify", [str(self.root)]),
        ):
            proc = subprocess.run(
                [sys.executable, str(self.root / "scripts" / name), *argv],
                cwd=self.root, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(
                proc.returncode, 0, name + ": " + proc.stdout + proc.stderr
            )
        self.assertEqual((self.root / "VERSION").read_text(), "0.2.0\n")

    # Generated by /ship coverage audit.
    # Value: protects=bump-version --check fails when a built JSON manifest's
    # version differs from VERSION, and skips unbuilt or non-JSON outputs;
    # fails_when=the version comparison or either skip guard in check() is
    # dropped or inverted; why_new=existing --check tests only hit the semver
    # guard and an empty generator list; seam=none
    def test_check_catches_manifest_version_drift(self):
        # check() loads scripts/build from disk, so register generators in
        # the temp copy's build file rather than patching the module.
        build = self.root / "scripts" / "build"
        build.write_text(
            build.read_text().replace(
                "GENERATORS = []",
                "GENERATORS = [lambda root: {\n"
                "    'plugin.json': '{\"version\": \"9.9.9\"}',\n"
                "    'unbuilt.json': '{\"version\": \"0.0.0\"}',\n"
                "    'notes.md': 'version: 0.0.0',\n"
                "}]",
                1,
            )
        )
        # CHANGELOG.md keeps its 0.1.0 heading: bump-version does not
        # read it, the release workflow owns it.
        (self.root / "VERSION").write_text("1.2.3\n")
        (self.root / "notes.md").write_text("version: 0.0.0\n")
        manifest = self.root / "plugin.json"
        manifest.write_text('{"name": "x", "version": "1.2.3"}\n')
        proc = call(self.bump, ["--check"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest.write_text('{"name": "x", "version": "1.2.2"}\n')
        proc = call(self.bump, ["--check"])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("plugin.json: version '1.2.2' != VERSION '1.2.3'", proc.stderr)
        self.assertNotIn("unbuilt.json", proc.stderr)
        self.assertNotIn("notes.md", proc.stderr)


class BuildManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        self.build = load_script(self.root, "build", "bt_build_under_test")

    def test_build_writes_files_and_never_deletes(self):
        self.build.GENERATORS = [lambda root: {"gen/out.txt": "v1\n"}]
        self.assertEqual(self.build.main([]), 0)
        self.assertEqual((self.root / "gen" / "out.txt").read_text(), "v1\n")
        self.assertFalse((self.root / ".generated-files").exists())
        self.assertEqual(self.build.main(["--check"]), 0)

        # A path dropped from the generators is left on disk: build never
        # deletes files.
        self.build.GENERATORS = [lambda root: {"gen/other.txt": "v2\n"}]
        self.assertEqual(self.build.main([]), 0)
        self.assertTrue((self.root / "gen" / "out.txt").is_file())
        self.assertEqual((self.root / "gen" / "other.txt").read_text(), "v2\n")
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_check_fails_on_drift_and_missing_output(self):
        self.build.GENERATORS = [lambda root: {"g.txt": "v1"}]
        self.assertEqual(self.build.main(["--check"]), 1)
        self.build.main([])
        (self.root / "g.txt").write_text("tampered")
        self.assertEqual(self.build.main(["--check"]), 1)
        self.build.main([])
        (self.root / "g.txt").unlink()
        self.assertEqual(self.build.main(["--check"]), 1)

    def test_bad_generated_paths_raise(self):
        for rel in ("../x", "/abs", ".git/HEAD"):
            with self.subTest(rel=rel):
                self.build.GENERATORS = [lambda root, rel=rel: {rel: "x\n"}]
                with self.assertRaises(ValueError):
                    call(self.build, [])
                with self.assertRaises(ValueError):
                    call(self.build, ["--check"])
                self.assertFalse((self.root / ".generated-files").exists())

    def test_bad_arg_exits_2_and_duplicate_relpath_raises(self):
        self.build.GENERATORS = [lambda root: {"g.txt": "v1\n"}]
        proc = call(self.build, ["--bogus"])
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("Usage", proc.stderr)
        self.assertEqual(call(self.build, ["--check", "extra"]).returncode, 2)
        self.assertFalse((self.root / "g.txt").exists())
        self.build.GENERATORS = [
            lambda root: {"g.txt": "a\n"},
            lambda root: {"g.txt": "b\n"},
        ]
        with self.assertRaises(ValueError) as cm:
            call(self.build, [])
        self.assertIn("two generators produce g.txt", str(cm.exception))
        self.assertFalse((self.root / "g.txt").exists())

    def test_cli_smoke(self):
        proc = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "build"), "--check"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
