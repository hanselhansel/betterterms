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


def make_repo_root(path):
    """Give a temp dir the files verify requires of a repo root."""
    (path / "VERSION").write_text("0.1.0\n")
    (path / "kit.config.json").write_text('{"name": "x"}\n')


class VerifyCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_repo_root(self.root)

    def add_skill(self, folder="betterterms-x", name="betterterms-x", extra_body=""):
        d = self.root / "skills" / folder
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(SKILL.format(name=name) + extra_body)

    def assert_failed(self, proc, check):
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(f"FAIL {check}", proc.stdout)

    def test_bad_root_exits_2(self):
        with tempfile.TemporaryDirectory() as empty:
            proc = run_verify(Path(empty))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(run_verify(self.root / "nonexistent").returncode, 2)
        no_kit = self.root / "kit.config.json"
        no_kit.unlink()
        self.assertEqual(run_verify(self.root).returncode, 2)

    def test_skill_names_mismatch_fails(self):
        self.add_skill(name="x")
        self.assert_failed(run_verify(self.root), "skill-names")

    def test_top_level_bin_fails(self):
        (self.root / "bin").mkdir()
        self.assert_failed(run_verify(self.root), "no-bin")

    def test_local_path_fails(self):
        (self.root / "notes.txt").write_text("built under /Users/hansel/repo\n")
        self.assert_failed(run_verify(self.root), "no-local-paths")

    def test_home_and_windows_paths_fail_but_tilde_dotfiles_pass(self):
        self.add_skill(extra_body="reads ~/.claude/settings.json at runtime\n")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL no-local-paths", proc.stdout)
        (self.root / "a.txt").write_text("see /home/hansel/repo\n")
        (self.root / "b.txt").write_text("see C:\\Users\\hansel\\repo\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("a.txt:1", proc.stdout)
        self.assertIn("b.txt:1", proc.stdout)

    def test_internal_docs_exempt_but_docs_guides_checked(self):
        research = self.root / "docs" / "research"
        research.mkdir(parents=True)
        (research / "notes.md").write_text("/Users/hansel/x and moreover.\n")
        proc = run_verify(self.root)
        self.assertNotIn("FAIL no-local-paths", proc.stdout)
        self.assertNotIn("FAIL prose-rules", proc.stdout)
        guides = self.root / "docs" / "guides"
        guides.mkdir(parents=True)
        (guides / "g.md").write_text("built under /Users/hansel/repo\n")
        self.assert_failed(run_verify(self.root), "no-local-paths")

    def test_em_dash_in_skill_markdown_fails(self):
        self.add_skill(extra_body="offer one \u2014 offer two\n")
        self.assert_failed(run_verify(self.root), "prose-rules")

    def test_banned_word_inflections_fail(self):
        for word in ("delving", "leveraged", "showcasing", "underscores", "fostering"):
            with self.subTest(word=word):
                (self.root / "README.md").write_text(f"We are {word} things.\n")
                self.assert_failed(run_verify(self.root), "prose-rules")

    def test_lowercase_claude_md_fails(self):
        (self.root / "claude.md").write_text("instructions\n")
        self.assert_failed(run_verify(self.root), "no-root-claude-md")

    def test_nested_venv_scanned_but_promptfoo_skipped(self):
        nested = self.root / "pkg" / ".venv"
        nested.mkdir(parents=True)
        (nested / "notes.md").write_text("has an em \u2014 dash\n")
        (self.root / ".promptfoo").mkdir()
        (self.root / ".promptfoo" / "out.md").write_text("has an em \u2014 dash\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertIn("pkg/.venv/notes.md", proc.stdout)
        self.assertNotIn(".promptfoo", proc.stdout)

    def test_git_ignored_files_are_not_scanned(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text("ignored.txt\n")
        (self.root / "ignored.txt").write_text("built under /Users/hansel/repo\n")
        (self.root / "seen.txt").write_text("built under /home/hansel/repo\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("seen.txt", proc.stdout)
        self.assertNotIn("ignored.txt", proc.stdout)

    def test_unknown_frontmatter_key_fails(self):
        self.write_skill(
            "---\nname: betterterms-x\ndescription: Does a thing.\nfoo: bar\n---\nbody\n"
        )
        self.assert_failed(run_verify(self.root), "skill-names")

    def test_plain_value_with_colon_space_fails(self):
        self.write_skill(
            "---\nname: betterterms-x\ndescription: a: b\n---\nbody\n"
        )
        proc = run_verify(self.root)
        self.assert_failed(proc, "skill-names")
        self.assertIn("needs quoting", proc.stdout)

    # Generated by /ship coverage audit.
    # Value: protects=verify fails when a CLAUDE.md or AGENTS.md exists anywhere
    # in the tree (README is the only instruction file); fails_when=the
    # no-root-claude-md check stops scanning subdirs or drops a filename;
    # why_new=no existing test touches no-root-claude-md; seam=none
    def test_nested_claude_md_and_agents_md_fail(self):
        (self.root / "CLAUDE.md").write_text("instructions\n")
        (self.root / "skills").mkdir()
        (self.root / "skills" / "AGENTS.md").write_text("instructions\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-root-claude-md")
        self.assertIn("CLAUDE.md", proc.stdout)
        self.assertIn("skills/AGENTS.md", proc.stdout)

    # Generated by /ship coverage audit.
    # Value: protects=prose-rules flags banned words in shipped markdown but
    # exempts internal docs/research; fails_when=BANNED_WORDS regex or the
    # PROSE_SKIP_PARTS exemption is broken; why_new=only the em dash rule is
    # tested; seam=none
    def test_banned_word_fails_except_in_internal_docs(self):
        research = self.root / "docs" / "research"
        research.mkdir(parents=True)
        (research / "notes.md").write_text("A robust survey.\n")
        self.assertEqual(run_verify(self.root).returncode, 0)
        (self.root / "README.md").write_text("We Leverage the floor.\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertIn("README.md:1: banned word 'Leverage'", proc.stdout)
        self.assertNotIn("notes.md", proc.stdout)

    # Generated by /ship coverage audit.
    # Value: protects=verify exits non-zero when the unit test suite fails;
    # fails_when=check_unit_tests ignores the unittest return code; why_new=
    # existing tests only hit the SKIP branch (no tests/ dir); seam=none
    def test_failing_unit_test_fails_verify(self):
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "test_broken.py").write_text(
            "import unittest\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_x(self):\n"
            "        self.assertEqual(1, 2)\n"
        )
        self.assert_failed(run_verify(self.root), "unit-tests")

    # Generated by /ship coverage audit.
    # Value: protects=each skill-names rule (prefix, SKILL.md, description,
    # 1024-char cap, 500-line body) and the 400-line source cap fail verify;
    # fails_when=any one guard in check_skill_names or check_file_size is
    # dropped or its limit drifts; why_new=only the name/folder mismatch rule
    # was tested; seam=none
    def test_bad_trees_fail_named_check(self):
        long_desc = "x" * 1025
        cases = [
            (
                "bad prefix",
                "skill-names",
                "must be betterterms-",
                lambda: self.add_skill(folder="other-x", name="other-x"),
            ),
            (
                "missing SKILL.md",
                "skill-names",
                "missing SKILL.md",
                lambda: (self.root / "skills" / "betterterms-x").mkdir(parents=True),
            ),
            (
                "missing description",
                "skill-names",
                "missing description",
                lambda: self.write_skill("---\nname: betterterms-x\n---\nbody\n"),
            ),
            (
                "long description",
                "skill-names",
                "1025 chars > 1024",
                lambda: self.write_skill(
                    f"---\nname: betterterms-x\ndescription: {long_desc}\n---\nbody\n"
                ),
            ),
            (
                "long body",
                "skill-names",
                "501 lines > 500",
                lambda: self.add_skill(extra_body="line\n" * 500),
            ),
            (
                "big source file",
                "file-size",
                "big.py (401 lines > 400)",
                lambda: (self.root / "big.py").write_text("x = 1\n" * 401),
            ),
        ]
        for label, check, message, build in cases:
            with self.subTest(label):
                with tempfile.TemporaryDirectory() as tmp:
                    self.root = Path(tmp)
                    make_repo_root(self.root)
                    build()
                    proc = run_verify(self.root)
                    self.assert_failed(proc, check)
                    self.assertIn(message, proc.stdout)

    def write_skill(self, text):
        d = self.root / "skills" / "betterterms-x"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(text)

    def test_clean_tree_passes(self):
        self.add_skill()
        proc = run_verify(self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()
