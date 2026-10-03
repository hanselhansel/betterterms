import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERIFY = REPO / "scripts" / "verify"

SKILL = """\
---
name: {name}
description: Test skill. Use when testing.
---
body
"""


def run_verify(root):
    return subprocess.run(
        [sys.executable, str(VERIFY), str(root)],
        capture_output=True,
        text=True,
        timeout=120,
    )


class VerifyCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def add_skill(self, folder="betterterms-x", name="betterterms-x", extra_body=""):
        d = self.root / "skills" / folder
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(SKILL.format(name=name) + extra_body)

    def assert_failed(self, proc, check):
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(f"FAIL {check}", proc.stdout)

    def test_skill_names_mismatch_fails(self):
        self.add_skill(name="x")
        self.assert_failed(run_verify(self.root), "skill-names")

    def test_top_level_bin_fails(self):
        (self.root / "bin").mkdir()
        self.assert_failed(run_verify(self.root), "no-bin")

    def test_local_path_fails(self):
        (self.root / "notes.txt").write_text("built under /Users/hansel/repo\n")
        self.assert_failed(run_verify(self.root), "no-local-paths")

    def test_em_dash_in_skill_markdown_fails(self):
        self.add_skill(extra_body="offer one \u2014 offer two\n")
        self.assert_failed(run_verify(self.root), "prose-rules")

    def test_clean_tree_passes(self):
        self.add_skill()
        proc = run_verify(self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()
