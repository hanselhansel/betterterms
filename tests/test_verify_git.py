"""Git-mode verify checks: file list comes from git ls-files, honoring
.gitignore, with the same skip rules applied on top."""

import os
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


def git_env():
    """os.environ minus every GIT_* variable, so a leaked GIT_DIR,
    GIT_INDEX_FILE or GIT_WORK_TREE cannot point a test's git commands
    at another repository."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


@unittest.skipUnless(shutil.which("git"), "git required")
class GitModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_repo_root(self.root)
        subprocess.run(
            [GIT, "init", "-q"], cwd=self.root, check=True, env=git_env()
        )

    def git(self, *args):
        subprocess.run(
            [GIT, *args], cwd=self.root, check=True, env=git_env()
        )

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
        self.git("add", "-A")
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
        self.git("add", "-A")
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
        self.git("add", "-A")
        proc = run_verify(self.root)
        assert_failed(self, proc, "vendor-sync")
        self.assertIn("extra.local", proc.stdout)

    def test_undecodable_filename_fails_instead_of_crashing(self):
        # A filename that is not valid UTF-8 reaches the checks via
        # surrogateescape and FAILs by name instead of crashing the
        # git file listing. Some filesystems (APFS) refuse such names;
        # texts() is still exercised directly below.
        try:
            fd = os.open(
                os.fsencode(self.root) + b"/bad-\xff-name.txt",
                os.O_CREAT | os.O_WRONLY,
                0o644,
            )
        except OSError:
            fd = None
        if fd is not None:
            os.write(fd, b"text\n")
            os.close(fd)
            proc = run_verify(self.root)
            assert_failed(self, proc, "no-local-paths")
            self.assertIn("undecodable filename", proc.stdout)
            self.assertIn("bad-", proc.stdout)
        # Direct unit-level check of the reporting path.
        bad = []
        rel = Path("bad-\udcff-name.txt")
        files = [self.root / rel]
        real = checks_scan.file_list
        checks_scan.file_list = lambda root: files
        try:
            out = list(checks_scan.texts(self.root, bad, lambda r: False))
        finally:
            checks_scan.file_list = real
            checks_scan.file_list.cache_clear()
        self.assertEqual(out, [])
        self.assertTrue(
            any("undecodable filename" in b and "bad-" in b for b in bad)
        )

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
