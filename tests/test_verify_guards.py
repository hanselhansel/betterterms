"""Verify hardening checks: decoded frontmatter strings, skill-name
fullmatch, data-file and skill-dir symlink guards, display() escaping,
home paths in parens and quotes, inflected banned words, and skip rules
applied to a full path rather than its parent."""

import os
import unittest
from pathlib import Path

from test_verify import (
    MAC_HOME,
    VerifyRepoCase,
    checks_scan,
    run_verify,
)


class FrontmatterStringScanTest(VerifyRepoCase):
    """Decoded SKILL.md frontmatter strings feed the content checks:
    escapes such as \\u2014 only appear after YAML parsing."""

    def write_escaped_skill(self, description):
        self.write_skill(
            "---\n"
            "name: betterterms-x\n"
            'description: "' + description + '"\n'
            "---\nbody\n"
        )

    def test_escaped_em_dash_and_banned_word_fail_prose_rules(self):
        self.write_escaped_skill("offer one \\u2014 offer two")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertIn("SKILL.md: frontmatter: em dash", proc.stdout)
        # \u0064 is 'd': the decoded value reads "a delving tool".
        self.write_escaped_skill("a \\u0064elving tool")
        proc = run_verify(self.root)
        self.assert_failed(proc, "prose-rules")
        self.assertIn("banned word 'delving'", proc.stdout)

    def test_escaped_home_path_fails_no_local_paths(self):
        self.write_escaped_skill("see \\u002fUsers\\u002fme")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        self.assertIn("SKILL.md: frontmatter", proc.stdout)


class InflectedBannedWordsTest(VerifyRepoCase):
    def test_inflected_forms_fail(self):
        for word in ("crucially", "robustness", "pivotally",
                     "comprehensively"):
            with self.subTest(word=word):
                (self.root / "README.md").write_text(f"A {word} claim.\n")
                proc = run_verify(self.root)
                self.assert_failed(proc, "prose-rules")
                self.assertIn(f"banned word '{word}'", proc.stdout)
                (self.root / "README.md").unlink()


class HomePathEdgesTest(VerifyRepoCase):
    def test_home_paths_in_parens_quotes_and_punctuation_fail(self):
        # /home/<name> used to need '/', whitespace or ':' after it, so
        # the same path inside parens or quotes slipped through.
        home = "/" + "home/hansel"
        for i, line in enumerate(
            (
                f"see ({home})",
                f'see "{home}"',
                f"see '{home}'",
                f"{home}, then more",
            )
        ):
            (self.root / f"h{i}.txt").write_text(line + "\n")
        proc = run_verify(self.root)
        self.assert_failed(proc, "no-local-paths")
        for i in range(4):
            self.assertIn(f"h{i}.txt:1", proc.stdout)
        (self.root / "u.txt").write_text(f"see ({MAC_HOME})\n")
        proc = run_verify(self.root)
        self.assertIn("u.txt:1", proc.stdout)


class SkillNameFullmatchTest(VerifyRepoCase):
    def test_folder_name_with_trailing_newline_fails(self):
        # re.match + $ accepts a trailing newline; fullmatch does not.
        d = self.root / "skills" / "betterterms-x\n"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            '---\nname: "betterterms-x\\n"\n'
            "description: Does a thing.\n---\nbody\n"
        )
        proc = run_verify(self.root)
        self.assert_failed(proc, "skill-names")
        self.assertIn("folder must be betterterms-", proc.stdout)


class DataFileSymlinkGuardTest(VerifyRepoCase):
    @unittest.skipIf(os.name == "nt", "needs POSIX symlinks")
    def test_prose_never_reads_through_linked_data_files(self):
        # A linked skills/**/*.json is never read through: its target's
        # contents must not reach prose-rules.
        self.add_skill()
        (self.root / "target.json").write_text('{"hint": "delving deep"}\n')
        (self.root / "skills" / "betterterms-x" / "data.json").symlink_to(
            "../../target.json"
        )
        proc = run_verify(self.root)
        self.assertIn("PASS prose-rules", proc.stdout)
        self.assert_failed(proc, "no-symlinks")
        self.assertIn("data.json", proc.stdout)


class FullPathSkipTest(VerifyRepoCase):
    def test_file_at_evals_holdout_is_skipped(self):
        # evals/holdout is a skipped path, not only a skipped directory:
        # a file (or link) there is never scanned.
        (self.root / "evals").mkdir()
        (self.root / "evals" / "holdout").write_text(
            f"built under {MAC_HOME}\n"
        )
        proc = run_verify(self.root)
        self.assertNotIn("FAIL no-local-paths", proc.stdout)
        self.assertNotIn("holdout", proc.stdout)


class DisplayEscapesTest(unittest.TestCase):
    def test_display_handles_non_ascii_and_surrogates(self):
        # vendor-sync calls display() on real filenames; a non-ASCII
        # name used to crash the ASCII decode even without surrogates.
        for name in ("caf\u00e9.py", "bad-\udcff-name.txt", "caf\u00e9\udcff"):
            with self.subTest(name=name):
                out = checks_scan.display(Path(name))
                self.assertTrue(all(ord(c) < 128 for c in out))
        self.assertIn("bad-", checks_scan.display(Path("bad-\udcff-name.txt")))


if __name__ == "__main__":
    unittest.main()
