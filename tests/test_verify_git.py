"""Git-mode verify checks: file list comes from git ls-files, honoring
.gitignore, with the same skip rules applied on top."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_verify import (
    GIT,
    MAC_HOME,
    UNIX_HOME,
    assert_failed,
    checks_scan,
    make_repo_root,
    run_verify,
)


@unittest.skipUnless(shutil.which("git"), "git required")
class GitModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_repo_root(self.root)
        subprocess.run([GIT, "init", "-q"], cwd=self.root, check=True)

    def test_git_ignored_files_are_not_scanned(self):
        (self.root / ".gitignore").write_text("ignored.txt\n")
        (self.root / "ignored.txt").write_text(f"built under {MAC_HOME}\n")
        (self.root / "seen.txt").write_text(f"built under {UNIX_HOME}\n")
        proc = run_verify(self.root)
        assert_failed(self, proc, "no-local-paths")
        self.assertIn("seen.txt", proc.stdout)
        self.assertNotIn("ignored.txt", proc.stdout)

    def test_tracked_dot_claude_files_fail_and_worktrees_skipped(self):
        wt = self.root / ".claude" / "worktrees" / "wt"
        wt.mkdir(parents=True)
        (wt / "notes.md").write_text("em \u2014 dash\n")
        (self.root / ".claude" / "CLAUDE.md").write_text("instructions\n")
        (self.root / ".claude" / "settings.json").write_text(
            f'{{"p": "{MAC_HOME}"}}\n'
        )
        subprocess.run([GIT, "add", "-A"], cwd=self.root, check=True)
        proc = run_verify(self.root)
        assert_failed(self, proc, "no-root-claude-md")
        self.assertIn(".claude/CLAUDE.md", proc.stdout)
        assert_failed(self, proc, "no-local-paths")
        self.assertIn(".claude/settings.json", proc.stdout)
        self.assertNotIn("worktrees", proc.stdout)

    def test_skip_dirs_filtered_in_git_mode(self):
        (self.root / ".venv").mkdir()
        (self.root / ".venv" / "bad.txt").write_text(f"{MAC_HOME}\n")
        nested = self.root / "pkg" / "node_modules"
        nested.mkdir(parents=True)
        (nested / "bad.txt").write_text(f"{MAC_HOME}\n")
        (self.root / "seen.txt").write_text(f"{MAC_HOME}\n")
        proc = run_verify(self.root)
        assert_failed(self, proc, "no-local-paths")
        self.assertIn("seen.txt", proc.stdout)
        self.assertNotIn(".venv", proc.stdout)
        self.assertNotIn("node_modules", proc.stdout)

    def test_tracked_evals_holdout_files_are_skipped(self):
        holdout = self.root / "evals" / "holdout"
        holdout.mkdir(parents=True)
        (holdout / "cases.md").write_text("em \u2014 dash\n")
        (self.root / "evals" / "scored.md").write_text("em \u2014 dash\n")
        subprocess.run([GIT, "add", "-A"], cwd=self.root, check=True)
        proc = run_verify(self.root)
        assert_failed(self, proc, "prose-rules")
        self.assertIn("evals/scored.md", proc.stdout)
        self.assertNotIn("holdout", proc.stdout)

    def test_vendor_sync_counts_git_ignored_drift(self):
        # A gitignored file inside a _vendor tree is invisible to
        # git ls-files, but the payload compare must still see it.
        btlib = self.root / "skills/betterterms-guardrails/scripts/btlib"
        canon = self.root / "scripts/_lib"
        for base in (btlib / "_vendor" / "yaml", canon / "_vendor" / "yaml"):
            base.mkdir(parents=True)
            (base / "a.py").write_text("A\n")
        (btlib / "yaml.py").write_text("same\n")
        (canon / "miniyaml.py").write_text("same\n")
        (self.root / ".gitignore").write_text("*.local\n")
        (btlib / "_vendor" / "yaml" / "extra.local").write_text("drift\n")
        subprocess.run([GIT, "add", "-A"], cwd=self.root, check=True)
        proc = run_verify(self.root)
        assert_failed(self, proc, "vendor-sync")
        self.assertIn("extra.local", proc.stdout)

    def test_git_file_list_computed_once_per_run(self):
        calls = []
        real = checks_scan.git_relpaths

        def counting(root):
            calls.append(root)
            return real(root)

        checks_scan.git_relpaths = counting
        try:
            run_verify(self.root)
        finally:
            checks_scan.git_relpaths = real
            checks_scan.file_list.cache_clear()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
