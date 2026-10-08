"""bump-version tests: --check drift, guarded writes, rollback and the
monotonic-version rule."""

import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from test_scripts import _raise, call, load_script, make_repo


class BumpVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        self.bump = load_script(self.root, "bump-version", "bt_bump_under_test")
        # Bump targets derive from the VERSION on disk, never a literal
        # that could collide with or regress the real version.
        v = (self.root / "VERSION").read_text().strip().split(".")
        self.next_version = f"{v[0]}.{v[1]}.{int(v[2]) + 1}"

    def stub_build_outputs(self, files=None, exc=None):
        """Swap the build-module loader so bump sees canned outputs (or
        a generator failure); the write-path guard stays real."""
        real_build = self.bump._build_module()
        fake = types.SimpleNamespace(
            expected=(
                lambda root, version=None: files
                if exc is None
                else _raise(exc)
            ),
            _check_write_path=real_build._check_write_path,
        )
        real = self.bump._build_module
        self.bump._build_module = lambda: fake
        self.addCleanup(setattr, self.bump, "_build_module", real)

    def test_bad_args_exit_2_without_writing(self):
        version_file = self.root / "VERSION"
        before = version_file.read_text()
        for bad in (
            "1.2",
            "v1.2.3",
            "latest",
            "1.2.3-rc.1",
            "1.2.3+build",
            "01.2.3",
            "1.02.3",
            "1.2.3 ",
            "1.2.3\n",
            "١.٢.٣",
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
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(
            (self.root / "VERSION").read_text(), self.next_version + "\n"
        )
        self.assertEqual((self.root / "gen" / "out.txt").read_text(), "v1\n")

    def test_bump_computes_outputs_before_any_write(self):
        # A generator failure leaves VERSION and the tree untouched.
        version_file = self.root / "VERSION"
        before = version_file.read_text()
        self.stub_build_outputs(exc=ValueError("two generators produce g.txt"))
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(version_file.read_text(), before)

    def test_bump_restores_touched_files_on_write_failure(self):
        # 'zz' exists as a file, so writing zz/x.txt fails mid-way after
        # a.txt and VERSION were already written: every touched file must
        # be restored (old bytes back, new files removed).
        (self.root / "a.txt").write_text("old a\n")
        (self.root / "zz").write_text("not a dir\n")
        version_before = (self.root / "VERSION").read_bytes()
        self.stub_build_outputs(
            {"a.txt": "new a\n", "b.txt": "new b\n", "zz/x.txt": "x\n"}
        )
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "VERSION").read_bytes(), version_before)
        self.assertEqual((self.root / "a.txt").read_text(), "old a\n")
        self.assertFalse((self.root / "b.txt").exists())

    def test_bump_stamps_new_version_into_generated_outputs(self):
        # Generators get the version explicitly: outputs computed for a
        # bump carry the NEW version even though VERSION on disk still
        # holds the old one while they are computed.
        build = self.root / "scripts" / "build"
        build.write_text(
            build.read_text().replace(
                "GENERATORS = []",
                "GENERATORS = [lambda root, version: {\n"
                "    'gen/version.txt': 'version ' + version + '\\n',\n"
                "    'gen/manifest.json': "
                "'{\"version\": \"' + version + '\"}',\n"
                "}]",
                1,
            )
        )
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(
            (self.root / "gen" / "version.txt").read_text(),
            f"version {self.next_version}\n",
        )
        self.assertEqual(
            call(self.bump, ["--check"]).returncode, 0
        )
        build_mod = load_script(self.root, "build", "bt_build_embedded")
        self.assertEqual(build_mod.main(["--check"]), 0)

    def test_bump_restores_missing_version_on_write_failure(self):
        (self.root / "VERSION").unlink()
        (self.root / "zz").write_text("not a dir\n")
        self.stub_build_outputs({"zz/x.txt": "x\n"})
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse((self.root / "VERSION").exists())

    @unittest.skipIf(os.name == "nt", "needs POSIX symlinks")
    def test_bump_refuses_symlinked_targets(self):
        # A generated path under a link, or VERSION itself as a link,
        # is refused before any write.
        real = self.root / "real"
        real.mkdir()
        (self.root / "gen").symlink_to(real, target_is_directory=True)
        version_before = (self.root / "VERSION").read_text()
        self.stub_build_outputs({"gen/out.txt": "x\n", "ok.txt": "y\n"})
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("symlink", proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), version_before)
        self.assertFalse((self.root / "ok.txt").exists())
        self.assertFalse((real / "out.txt").exists())
        # VERSION itself a link is refused with nothing else to write.
        (self.root / "gen").unlink()
        (self.root / "VERSION").unlink()
        (self.root / "VERSION").symlink_to(real / "V")
        self.stub_build_outputs({})
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse((real / "V").exists())

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
        # Extended by /ship coverage audit.
        # Value: protects=--check exits 2 naming a missing VERSION instead of
        # crashing; fails_when=the is_file guard in check() is removed;
        # why_new=only malformed VERSION contents were tested; seam=none
        (self.root / "VERSION").unlink()
        proc = call(self.bump, ["--check"])
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("VERSION file missing", proc.stderr)

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
            ("bump-version", [self.next_version]),
            ("verify", [str(self.root)]),
        ):
            proc = subprocess.run(
                [sys.executable, str(self.root / "scripts" / name), *argv],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                proc.returncode, 0, name + ": " + proc.stdout + proc.stderr
            )
        self.assertEqual(
            (self.root / "VERSION").read_text(), self.next_version + "\n"
        )

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
                "GENERATORS = [lambda root, version: {\n"
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

    def test_bump_refuses_same_or_lower_version(self):
        # A bump that does not move the version forward is a usage
        # error, not a silent rewrite.
        cur = (self.root / "VERSION").read_text().strip()
        v = [int(x) for x in cur.split(".")]
        lower = (
            f"{v[0]}.{v[1]}.{v[2] - 1}"
            if v[2]
            else f"{v[0]}.{v[1] - 1}.{v[2]}"
        )
        self.stub_build_outputs({})
        for bad in (cur, lower):
            with self.subTest(version=bad):
                proc = call(self.bump, [bad])
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("not above", proc.stderr)
                self.assertEqual(
                    (self.root / "VERSION").read_text().strip(), cur
                )

    def test_bump_refuses_non_regular_targets_before_writing(self):
        # A directory at a write path, or a FIFO whose open would block
        # forever, is refused before VERSION or anything else is written.
        version_before = (self.root / "VERSION").read_text()
        (self.root / "adir").mkdir()
        self.stub_build_outputs({"adir": "x\n", "ok.txt": "y\n"})
        proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("not a regular file", proc.stderr)
        self.assertEqual((self.root / "VERSION").read_text(), version_before)
        self.assertFalse((self.root / "ok.txt").exists())
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.root / "pipe")
            self.stub_build_outputs({"pipe": "x\n"})
            proc = call(self.bump, [self.next_version])
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("not a regular file", proc.stderr)

    def test_rollback_attempts_every_restore_and_reraises(self):
        # A restore that itself fails must not stop the remaining
        # restores or mask the original write error.
        (self.root / "a.txt").write_text("old a\n")
        (self.root / "zz").write_text("not a dir\n")
        self.stub_build_outputs(
            {"a.txt": "new a\n", "b.txt": "new b\n", "zz/x.txt": "x\n"}
        )

        def fail_write_bytes(self, data):
            raise OSError("read-only fs")

        def fail_unlink(self, missing_ok=False):
            raise OSError("file busy")

        with mock.patch.object(Path, "write_bytes", fail_write_bytes):
            with mock.patch.object(Path, "unlink", fail_unlink):
                proc = call(self.bump, [self.next_version])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        for frag in ("VERSION", "a.txt", "b.txt", "zz/x.txt"):
            self.assertIn(frag, proc.stderr)
        self.assertIn("bump-version:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
