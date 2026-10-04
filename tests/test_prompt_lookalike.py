"""Lookalike handling in the UserPromptSubmit hook (spec 6.8).

A ``bt <verb>`` lookalike blocks only when the trimmed message starts
with ``bt <verb>`` (one leading backtick or a leading slash allowed)
and carries the piece the verb needs: a digit for floor, a hex token
of six or more characters for approve/reject, ``=`` for terms.
Everything else is prose and passes untouched. Shared helpers live in
tests/test_prompt_commands.py.
"""

import unittest

from bt_helpers import REPO, BtTestCase
from test_prompt_commands import run_hook, hook_json


class LookalikeBlockTest(BtTestCase):
    def make_case(self, cid="case-1"):
        d = self.home / "cases" / cid
        d.mkdir(parents=True)
        return d

    def test_backticked_floor_lookalike_blocks(self):
        # A backtick-wrapped line still starts with the verb shape and
        # carries an amount-like digit: block, never write the floor.
        d = self.make_case()
        proc = run_hook(self.home, "`bt floor case-1 62`")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])
        self.assertNotIn("62", proc.stdout)
        self.assertFalse((d / ".floor").exists())

    def test_slashed_floor_lookalike_blocks(self):
        d = self.make_case()
        proc = run_hook(self.home, "/bt floor case-1 62")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])
        self.assertFalse((d / ".floor").exists())

    def test_floor_lookalike_with_trailing_words_blocks(self):
        d = self.make_case()
        proc = run_hook(
            self.home, "bt floor case-1 sixty two dollars 62"
        )
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])
        self.assertFalse((d / ".floor").exists())

    def test_approve_lookalike_with_hex_blocks(self):
        self.make_case()
        proc = run_hook(
            self.home, "bt approve case-1 abcd1234 extra words"
        )
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt approve", out["reason"])

    def test_terms_lookalike_with_equals_blocks(self):
        self.make_case()
        proc = run_hook(
            self.home, "bt terms case-1 target=60 note extra"
        )
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt terms", out["reason"])


class ProsePassTest(BtTestCase):
    def make_case(self, cid="case-1"):
        d = self.home / "cases" / cid
        d.mkdir(parents=True)
        return d

    def test_bt_mentions_mid_sentence_pass(self):
        # `bt <verb>` inside ordinary prose is chat text, not a
        # command attempt; the hook stays silent.
        self.make_case()
        for prompt in (
            "The BT reject rate was high",
            "Can you explain how the bt floor command works?",
            "rename `bt approve` to bt ok in the README",
            'git commit -m "fix bt terms parsing"',
            "ok bt floor case-1 62",
            "please run bt approve case-1 abcd1234 now",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), "")

    def test_lookalike_without_the_marker_piece_passes(self):
        # A message that starts with the verb but lacks the piece the
        # verb needs is a question about the command, not an attempt.
        self.make_case()
        for prompt in (
            "bt floor",
            "bt floors are rising",       # the verb is not 'floor'
            "bt approve",                 # no 6+ hex token
            "bt reject",                  # nothing at all
            "bt approve case-1",          # case and no hex
            "bt terms case-1 now",        # no '='
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
