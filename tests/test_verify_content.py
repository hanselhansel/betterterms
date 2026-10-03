"""Content-scanning verify checks: local-path patterns, UTF-8 decoding,
vendor roots, evals holdout and vendor-sync drift."""

import tempfile
import unittest
from pathlib import Path

from test_verify import (
    FILE_URI_HOME,
    MAC_HOME,
    UNIX_HOME,
    WIN_HOME_FWD,
    VerifyRepoCase,
    make_repo_root,
    run_verify,
)


class VerifyContentTest(VerifyRepoCase):
    def test_file_uri_eol_home_and_forward_slash_windows_fail(self):
        (self.root / "f.txt").write_text(f"see {FILE_URI_HOME}\n")
        (self.root / "h.txt").write_text(f"home is {UNIX_HOME[:-5]}")
        (self.root / "w.txt").write_text(f"see {WIN_HOME_FWD}\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("f.txt:1", proc.stdout)
        self.assertIn("h.txt:1", proc.stdout)
        self.assertIn("w.txt:1", proc.stdout)

    def test_non_utf8_text_file_fails_but_binary_skipped(self):
        (self.root / "img.bin").write_bytes(b"\x89PNG\x00\x0d\x0a\x1a\x0a")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL", proc.stdout)
        (self.root / "latin.txt").write_bytes(b"caf\xe9\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("latin.txt: not valid UTF-8", proc.stdout)

    def test_non_utf8_md_and_py_fail_prose_rules_and_file_size(self):
        (self.root / "doc.md").write_bytes(b"text \xe9\n")
        (self.root / "code.py").write_bytes(b"x = '\xe9'\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertIn("doc.md: not valid UTF-8", proc.stdout)
        self.assert_failed(proc, "file-size")
        self.assertIn("code.py: not valid UTF-8", proc.stdout)

    def test_unit_tests_fails_when_zero_tests_run(self):
        (self.root / "tests").mkdir()
        proc = run_verify(self.root)
        self.assert_failed(proc, "unit-tests")
        self.assertIn("0 tests", proc.stdout)

    def test_skill_name_rejects_bad_hyphens_and_long_names(self):
        for folder in (
            "betterterms-x-", "betterterms-x--y", "betterterms--x",
            "betterterms-" + "x" * 53,
        ):
            with self.subTest(folder=folder):
                with tempfile.TemporaryDirectory() as tmp:
                    self.root = Path(tmp)
                    make_repo_root(self.root)
                    self.add_skill(folder=folder, name=folder)
                    self.assert_failed(run_verify(self.root), "skill-names")

    def test_vendor_exemption_applies_only_to_known_roots(self):
        other = self.root / "other" / "_vendor"
        other.mkdir(parents=True)
        (other / "notes.md").write_text(f"built under {MAC_HOME} \u2014 delving\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("other/_vendor/notes.md:1", proc.stdout)
        self.assert_failed(proc, "prose-rules")

    def test_evals_holdout_skipped_but_evals_scanned(self):
        holdout = self.root / "evals" / "holdout"
        holdout.mkdir(parents=True)
        (holdout / "cases.md").write_text("em \u2014 dash\n")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL prose-rules", proc.stdout)
        (self.root / "evals" / "scored.md").write_text("em \u2014 dash\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertNotIn("holdout", proc.stdout)

    def test_nul_or_utf_bom_in_text_named_file_fails(self):
        # NUL bytes under a text name fail every check that reads it:
        # no-local-paths (.md/.py/.js all scan), prose-rules (.md) and
        # file-size (.py/.js).
        (self.root / "nul.md").write_bytes(b"a\x00b\n")
        (self.root / "nul.py").write_bytes(b"x = 'a\x00b'\n")
        (self.root / "app.js").write_bytes(b"let x = 'a\x00b';\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assert_failed(proc, "prose-rules")
        self.assert_failed(proc, "file-size")
        for name in ("nul.md", "nul.py", "app.js"):
            self.assertIn(name, proc.stdout)
        # A UTF-16 or UTF-32 BOM counts too, on a text suffix or on an
        # extensionless scripts/ entry point.
        for name in ("nul.md", "nul.py", "app.js"):
            (self.root / name).unlink()
        (self.root / "bom.yaml").write_bytes(
            b"\xff\xfea\x00:\x00 \x001\x00\n\x00"
        )
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "tool").write_bytes(b"\xfe\xff\x00x\x00=\x001\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("bom.yaml", proc.stdout)
        self.assertIn("scripts/tool", proc.stdout)
        # Binary files under non-text names still skip silently.
        (self.root / "bom.yaml").unlink()
        (self.root / "scripts" / "tool").unlink()
        (self.root / "raw.bin").write_bytes(b"\x00\x01\x02")
        (self.root / "blob.bin").write_bytes(b"\x89PNG\x00rest")
        proc = run_verify(self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_utf16_bom_file_fails_as_not_utf8_regardless_of_suffix(self):
        # .sh is not a text suffix, but a UTF-16 BOM still marks the file
        # as text: it is read, not skipped, and fails UTF-8 decoding.
        (self.root / "deploy.sh").write_bytes(
            ("# see " + MAC_HOME + "\n").encode("utf-16")
        )
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("deploy.sh: not valid UTF-8", proc.stdout)

    def test_vendor_sync_ignores_junk_and_names_first_drift(self):
        # A NON-empty vendored tree: two small files mirrored both ways.
        btlib = self.root / "skills/betterterms-guardrails/scripts/btlib"
        canon = self.root / "scripts/_lib"
        for base in (btlib / "_vendor" / "yaml", canon / "_vendor" / "yaml"):
            base.mkdir(parents=True)
            (base / "a.py").write_text("A\n")
            (base / "b.py").write_text("B\n")
        (btlib / "yaml.py").write_text("same\n")
        (canon / "miniyaml.py").write_text("same\n")
        # OS cruft, editor swap files and __pycache__ do not count as drift.
        (btlib / "_vendor" / "yaml" / ".DS_Store").write_bytes(b"junk\x00")
        (canon / "_vendor" / "yaml" / "a.py.swp").write_text("swap\n")
        (canon / "_vendor" / "yaml" / "c.py~").write_text("backup\n")
        pycache = btlib / "_vendor" / "yaml" / "__pycache__"
        pycache.mkdir()
        (pycache / "a.cpython-311.pyc").write_bytes(b"\x00compiled")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL vendor-sync", proc.stdout)
        (btlib / "_vendor" / "yaml" / "b.py").write_text("drifted\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "vendor-sync")
        self.assertIn("b.py", proc.stdout)


if __name__ == "__main__":
    unittest.main()
