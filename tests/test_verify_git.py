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
    SKILL,
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
        subprocess.run([GIT, "init", "-q"], cwd=self.root, check=True, env=git_env())

    def git(self, *args):
        subprocess.run([GIT, *args], cwd=self.root, check=True, env=git_env())

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
        (self.root / ".claude" / "settings.json").write_text(f'{{"p": "{MAC_HOME}"}}\n')
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
        self.assertTrue(any("undecodable filename" in b and "bad-" in b for b in bad))

    @unittest.skipIf(os.name == "nt", "needs POSIX symlinks")
    def test_symlinks_fail_no_symlinks(self):
        # The repo holds no symlinks at all: tracked and untracked file
        # links, dir links and dangling links are each named, while the
        # other checks stay silent about them.
        real = self.root / "real"
        real.mkdir()
        (real / "f.txt").write_text("x\n")
        (self.root / "file-link").symlink_to("VERSION")
        (self.root / "dir-link").symlink_to(
            "real", target_is_directory=True
        )
        (self.root / "dangling").symlink_to("no-such-target")
        self.git("add", "-A")
        (self.root / "untracked-link").symlink_to("VERSION")
        proc = run_verify(self.root)
        assert_failed(self, proc, "no-symlinks")
        for name in ("file-link", "dir-link", "dangling", "untracked-link"):
            self.assertIn(name, proc.stdout)
        self.assertIn("PASS no-local-paths", proc.stdout)
        self.assertIn("PASS prose-rules", proc.stdout)

    def test_index_symlink_checked_out_as_file_fails(self):
        # A 120000 index entry checked out as a plain file (the
        # core.symlinks=false shape) is invisible to islink, but the
        # index mode still gives the link away.
        (self.root / "plain-link").write_text("VERSION\n")
        sha = subprocess.run(
            [GIT, "hash-object", "-w", "--stdin"],
            cwd=self.root, input="VERSION", text=True,
            capture_output=True, check=True, env=git_env(),
        ).stdout.strip()
        self.git(
            "update-index", "--add", "--cacheinfo", f"120000,{sha},plain-link"
        )
        proc = run_verify(self.root)
        assert_failed(self, proc, "no-symlinks")
        self.assertIn("plain-link", proc.stdout)
        self.assertIn("PASS no-local-paths", proc.stdout)

    def test_untracked_file_at_evals_holdout_is_skipped(self):
        # evals/holdout is a skipped path, not only a skipped dir: a
        # file or link there never reaches the content checks.
        (self.root / "evals").mkdir()
        (self.root / "evals" / "holdout").write_text(f"{MAC_HOME}\n")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL no-local-paths", proc.stdout)

    @unittest.skipIf(os.name == "nt", "needs POSIX symlinks")
    def test_skill_names_does_not_descend_linked_skill_dir(self):
        # The index remembers a real skills/betterterms-ln/SKILL.md while
        # the worktree now has that folder as a link; the skill-dir guard
        # keeps check_skill_names from reading through it.
        d = self.root / "skills" / "betterterms-ln"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(SKILL.format(name="betterterms-ln"))
        self.git("add", "-A")
        (d / "SKILL.md").unlink()
        d.rmdir()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "SKILL.md").write_text(SKILL.format(name="other-name"))
        (self.root / "skills" / "betterterms-ln").symlink_to(
            elsewhere, target_is_directory=True
        )
        proc = run_verify(self.root)
        assert_failed(self, proc, "no-symlinks")
        self.assertIn("PASS skill-names", proc.stdout)

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


class GitFallbackTest(unittest.TestCase):
    # Generated by /ship coverage audit.
    # Value: protects=when git ls-files fails (dangling worktree .git file)
    # verify falls back to os.walk and still FAILs a local path;
    # fails_when=git_relpaths drops its returncode guard, so the scan list
    # is empty and every content check passes silently; why_new=tests cover
    # a working git repo and a root with no .git only; seam=none
    def test_broken_git_marker_falls_back_to_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo_root(root)
            # A real worktree marker holds an absolute local path.
            (root / ".git").write_text(f"gitdir: {MAC_HOME}/.git/worktrees/x\n")
            (root / "notes.txt").write_text(f"built under {MAC_HOME}\n")
            self.assertIsNone(checks_scan.git_relpaths(root))
            proc = run_verify(root)
            assert_failed(self, proc, "no-local-paths")
            self.assertIn("notes.txt:1", proc.stdout)
            # The .git marker file itself is never scanned, though it
            # names a local path.
            self.assertNotIn(".git", proc.stdout)


if __name__ == "__main__":
    unittest.main()
