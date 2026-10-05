"""Lookalike handling in the UserPromptSubmit hook (spec 6.8).

A message that is not a whole-line command still blocks when it
claims to be one:

- floor: the words ``bt`` and ``floor`` adjacent (any whitespace, any
  case) anywhere in the message -- any line, after any prefix or
  markdown -- plus any digit in the message. The block reason never
  repeats the message.
- approve, reject, terms: the trimmed text starts with ``bt <verb>``
  (one leading backtick or a leading slash allowed) and carries the
  piece the verb needs: a hex token of six or more characters for
  approve/reject, ``=`` for terms.

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

    def test_floor_words_anywhere_with_a_digit_block(self):
        # `bt` and `floor` adjacent anywhere in the message plus any
        # digit claims to set the walk-away but is not the command:
        # block with the usage line, never write the amount, and
        # never echo it in the reason.
        d = self.make_case()
        for prompt in (
            "ok bt floor case-1 62",
            "hi\nbt floor case-1 62",
            "``bt floor case-1 62``",
            "> bt floor case-1 62",
            "**bt floor** case-1 62",
            "`bt floor case-1 62`",
            "/bt floor case-1 62",
            "bt floor case-1 sixty two dollars 62",
            "tell them bt\nfloor is 62",
            "the bt floor amount is 62 dollars",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                out = hook_json(proc)
                self.assertEqual(out["decision"], "block")
                self.assertIn("bt floor", out["reason"])
                self.assertNotIn("62", proc.stdout)
                self.assertFalse((d / ".floor").exists())

    def test_floor_command_shape_still_writes_the_floor(self):
        # Extra whitespace, a tab, or uppercase still fullmatch the
        # grammar: these are the real command, so the walk-away is
        # saved through stdin and the prompt blocks without echoing
        # the amount.
        d = self.make_case()
        for prompt in (
            "bt  floor case-1 62",
            "bt\tfloor case-1 62",
            "BT FLOOR case-1 62",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                out = hook_json(proc)
                self.assertEqual(out["decision"], "block")
                self.assertNotIn("62", proc.stdout)
                self.assertTrue((d / ".floor").exists())

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


class EnvelopeBackstopTest(BtTestCase):
    """Wake-envelope strictness and the shared floor backstop.

    A prompt counts as a Projects wake envelope only when its trimmed
    text starts with ``<wake`` and carries a ``<message`` element; a
    ``<wake`` substring anywhere else is plain text. The floor rule
    runs before any command is handled and scans the text of every
    ``from="human"`` message in an envelope -- the whole prompt when
    it is not one. Agent-authored text never counts, and digits that
    are part of a case-id token (``name-YYYYMMDD-xxxx``) are not the
    walk-away.
    """

    def make_case(self, cid="case-1"):
        d = self.home / "cases" / cid
        d.mkdir(parents=True)
        return d

    def test_envelope_human_floor_line_blocks_despite_terms_trigger(self):
        # The review probe: an earlier human floor line sits in the
        # envelope beside a triggering `bt terms`. The backstop scans
        # every human message before any command runs, so the
        # walk-away number never reaches the model and the terms
        # write never happens.
        case_dir = self.make_case()
        envelope = (
            '<wake reason="thread-reply">'
            '<message from="agent">your draft is ready</message>'
            '<message from="human">bt floor case-1 62</message>'
            '<message from="human" trigger="true">'
            "bt terms case-1 target=60</message>"
            "</wake>"
        )
        proc = run_hook(self.home, envelope)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])
        self.assertNotIn("62", proc.stdout)
        self.assertFalse((case_dir / ".floor").exists())
        self.assertFalse((case_dir / "plan.yaml").exists())

    def test_envelope_agent_floor_text_is_ignored(self):
        # The backstop reads human text only: an agent message quoting
        # the floor command never trips it, and an innocent human
        # trigger passes silently.
        self.make_case()
        envelope = (
            '<wake reason="thread-reply">'
            '<message from="agent">'
            "type bt floor case-1 62 to set it</message>"
            '<message from="human" trigger="true">'
            "ok, done. what next?</message>"
            "</wake>"
        )
        proc = run_hook(self.home, envelope)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_case_id_digits_never_trip_the_floor_rule(self):
        # `bt floor <case-id>` alone carries digits only inside the
        # id itself (name-YYYYMMDD-xxxx), not a number the user typed:
        # the message is prose and passes untouched.
        self.make_case()
        for prompt in (
            "bt floor acme-20261005-ab12",
            "set it with bt floor acme-20261005-ab12 later",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), "")

    def test_trailing_wake_tag_does_not_dodge_approve_usage(self):
        # Strict envelope parse: `<wake` mid-prompt is plain text, so
        # the start-anchored approve lookalike still blocks with its
        # usage line.
        self.make_case()
        proc = run_hook(
            self.home, "bt approve case-1 abcd1234 extra <wake"
        )
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt approve", out["reason"])

    def test_trailing_wake_tag_is_not_an_envelope(self):
        # `bt floor ... <wake` does not start with `<wake`, so it is
        # the user's own text, not an envelope: the floor lookalike
        # blocks it, and the amount is never written or echoed.
        d = self.make_case()
        proc = run_hook(
            self.home, "bt floor c-20261005-abcd 500 <wake"
        )
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])
        self.assertNotIn("500", proc.stdout)
        self.assertFalse((d / ".floor").exists())

    def test_wakeup_tag_is_not_an_envelope(self):
        # `<wakeup>` sits mid-prompt and carries no <message> element:
        # the whole prompt is user text and the raw floor backstop
        # still blocks on `bt floor` plus the digit.
        d = self.make_case()
        proc = run_hook(
            self.home, "note <wakeup> bt floor c-20261005-abcd 500"
        )
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])
        self.assertNotIn("500", proc.stdout)
        self.assertFalse((d / ".floor").exists())

    def test_wake_prefix_without_message_is_plain_text(self):
        # A prompt starting `<wake` but carrying no <message> element
        # is not an envelope at all: it is the user's own text.
        self.make_case()
        proc = run_hook(self.home, "<wakeup> bt floor case-1 62")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])


class ProsePassTest(BtTestCase):
    def make_case(self, cid="case-1"):
        d = self.home / "cases" / cid
        d.mkdir(parents=True)
        return d

    def test_bt_mentions_mid_sentence_pass(self):
        # approve/reject/terms keep the start-anchored rule: `bt
        # <verb>` inside ordinary prose is chat text, not a command
        # attempt; the hook stays silent.
        self.make_case()
        for prompt in (
            "The BT reject rate was high",
            "Can you explain how the bt floor command works?",
            "rename `bt approve` to bt ok in the README",
            'git commit -m "fix bt terms parsing"',
            "please run bt approve case-1 abcd1234 now",
            "the bt floor plan has no number in it",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), "")

    def test_lookalike_without_the_marker_piece_passes(self):
        # A message that starts with the verb but lacks the piece the
        # verb needs is a question about the command, not an attempt;
        # floor needs a digit anywhere in the message.
        self.make_case()
        for prompt in (
            "bt floor",
            "bt floor is set in the terminal",
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
