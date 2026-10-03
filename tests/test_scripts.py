import contextlib
import importlib.machinery
import importlib.util
import io
import os
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


class BuildManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        self.build = load_script(self.root, "build", "bt_build_under_test")

    def test_build_writes_files_and_never_deletes(self):
        self.build.GENERATORS = [
            lambda root, version: {"gen/out.txt": "v1\n"}
        ]
        self.assertEqual(self.build.main([]), 0)
        self.assertEqual((self.root / "gen" / "out.txt").read_text(), "v1\n")
        self.assertFalse((self.root / ".generated-files").exists())
        self.assertEqual(self.build.main(["--check"]), 0)

        # A path dropped from the generators is left on disk: build never
        # deletes files.
        self.build.GENERATORS = [
            lambda root, version: {"gen/other.txt": "v2\n"}
        ]
        self.assertEqual(self.build.main([]), 0)
        self.assertTrue((self.root / "gen" / "out.txt").is_file())
        self.assertEqual((self.root / "gen" / "other.txt").read_text(), "v2\n")
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_check_fails_on_drift_and_missing_output(self):
        self.build.GENERATORS = [lambda root, version: {"g.txt": "v1"}]
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
                self.build.GENERATORS = [
                    lambda root, version, rel=rel: {rel: "x\n"}
                ]
                with self.assertRaises(ValueError):
                    call(self.build, [])
                with self.assertRaises(ValueError):
                    call(self.build, ["--check"])
                self.assertFalse((self.root / ".generated-files").exists())

    def test_dotgit_segment_anywhere_and_any_case_raises(self):
        # Only the first segment was checked before; a nested or
        # differently-cased .git is just as off-limits.
        for rel in ("x/.GIT/HEAD", "a/.Git/config", "sub/.git/hooks/x"):
            with self.subTest(rel=rel):
                self.build.GENERATORS = [
                    lambda root, version, rel=rel: {rel: "x\n"}
                ]
                with self.assertRaises(ValueError):
                    call(self.build, [])
                with self.assertRaises(ValueError):
                    call(self.build, ["--check"])

    def test_unnormalized_and_reserved_paths_raise(self):
        # A path that changes under PurePosixPath normalization could
        # alias another generated file; VERSION and kit.config.json are
        # maintained by hand / bump-version, never by generators.
        version_before = (self.root / "VERSION").read_bytes()
        for rel in (
            "a//b.txt",
            "./x.txt",
            "a/./b.txt",
            "x/",
            "VERSION",
            "kit.config.json",
            "Kit.Config.Json",
        ):
            with self.subTest(rel=rel):
                self.build.GENERATORS = [
                    lambda root, version, rel=rel: {rel: "x\n"}
                ]
                with self.assertRaises(ValueError):
                    call(self.build, [])
                with self.assertRaises(ValueError):
                    call(self.build, ["--check"])
        self.assertEqual((self.root / "VERSION").read_bytes(), version_before)

    def test_duplicate_after_lowercasing_raises(self):
        # Case-only differences collide on case-insensitive filesystems.
        self.build.GENERATORS = [
            lambda root, version: {"X.txt": "a\n"},
            lambda root, version: {"x.txt": "b\n"},
        ]
        with self.assertRaises(ValueError) as cm:
            call(self.build, [])
        self.assertIn("two generators produce x.txt", str(cm.exception))
        self.assertFalse((self.root / "X.txt").exists())
        self.assertFalse((self.root / "x.txt").exists())

    def test_build_refuses_non_regular_targets(self):
        # A directory at a write path, or a FIFO whose open would block
        # forever, is refused before anything is written.
        (self.root / "adir").mkdir()
        self.build.GENERATORS = [
            lambda root, version: {"adir": "x\n", "ok.txt": "y\n"}
        ]
        with self.assertRaises(ValueError):
            call(self.build, [])
        self.assertFalse((self.root / "ok.txt").exists())
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.root / "pipe")
            self.build.GENERATORS = [lambda root, version: {"pipe": "x\n"}]
            with self.assertRaises(ValueError):
                call(self.build, [])

    @unittest.skipIf(os.name == "nt", "needs POSIX symlinks")
    def test_build_refuses_symlinked_targets(self):
        # A generated path that is a link or sits under one is refused
        # before any file is written.
        real = self.root / "real"
        real.mkdir()
        (self.root / "gen").symlink_to(real, target_is_directory=True)
        self.build.GENERATORS = [
            lambda root, version: {"gen/out.txt": "x\n", "ok.txt": "y\n"}
        ]
        with self.assertRaises(ValueError):
            call(self.build, [])
        self.assertFalse((self.root / "ok.txt").exists())
        self.assertFalse((real / "out.txt").exists())
        # The path itself as a link, or an escaping parent link, fail.
        (self.root / "gen").unlink()
        (self.root / "ok.txt").symlink_to(real / "out.txt")
        self.build.GENERATORS = [lambda root, version: {"ok.txt": "y\n"}]
        with self.assertRaises(ValueError):
            call(self.build, [])
        self.assertFalse((real / "out.txt").exists())
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (self.root / "esc").symlink_to(outside, target_is_directory=True)
        self.build.GENERATORS = [lambda root, version: {"esc/x.txt": "x\n"}]
        with self.assertRaises(ValueError):
            call(self.build, [])
        self.assertFalse((outside / "x.txt").exists())

    def test_bad_arg_exits_2_and_duplicate_relpath_raises(self):
        self.build.GENERATORS = [lambda root, version: {"g.txt": "v1\n"}]
        proc = call(self.build, ["--bogus"])
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("Usage", proc.stderr)
        self.assertEqual(call(self.build, ["--check", "extra"]).returncode, 2)
        self.assertFalse((self.root / "g.txt").exists())
        self.build.GENERATORS = [
            lambda root, version: {"g.txt": "a\n"},
            lambda root, version: {"g.txt": "b\n"},
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
