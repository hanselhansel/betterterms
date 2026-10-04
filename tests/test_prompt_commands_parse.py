"""Pure parse coverage for the UserPromptSubmit hook: the ``bt ...``
grammar and the wake-envelope ``user_text`` extraction. Hook behavior
lives in test_prompt_commands.py (split for the 400-line cap).
"""

import sys
import unittest

from bt_helpers import REPO

sys.path.insert(0, str(REPO / "hooks"))
import prompt_commands  # noqa: E402

WAKE = (
    '<wake reason="thread-reply">'
    '<message from="agent">{agent}</message>'
    '<message from="human" trigger="true">{human}</message>'
    "</wake>"
)


class ParseTest(unittest.TestCase):
    def test_parse_grammar(self):
        self.assertEqual(
            prompt_commands.parse("bt approve case-1 abcd1234"),
            {
                "verb": "approve",
                "case_id": "case-1",
                "hash8": "abcd1234",
            },
        )
        self.assertEqual(
            prompt_commands.parse("  BT FLOOR case-1 $62  "),
            {"verb": "floor", "case_id": "case-1", "amount": "$62"},
        )
        self.assertEqual(
            prompt_commands.parse(
                "bt terms case-1 target=60 alternative=50"
            ),
            {
                "verb": "terms",
                "case_id": "case-1",
                "target": "60",
                "alternative": "50",
            },
        )
        self.assertEqual(
            prompt_commands.parse(
                "bt terms case-1 alternative=50 target=60"
            ),
            {
                "verb": "terms",
                "case_id": "case-1",
                "target": "60",
                "alternative": "50",
            },
        )
        self.assertEqual(
            prompt_commands.parse("bt terms case-1 target=60"),
            {
                "verb": "terms",
                "case_id": "case-1",
                "target": "60",
                "alternative": None,
            },
        )
        self.assertIsNone(
            prompt_commands.parse("bt terms case-1 target=1 target=2")
        )
        self.assertIsNone(
            prompt_commands.parse("bt terms case-1 bogus=1")
        )
        self.assertIsNone(prompt_commands.parse("hello"))
        self.assertIsNone(
            prompt_commands.parse("bt approve case-1")
        )
        self.assertIsNone(
            prompt_commands.parse("bt frobnicate case-1 62")
        )

    def test_user_text_whole_prompt(self):
        self.assertEqual(
            prompt_commands.user_text("bt floor case-1 62"),
            "bt floor case-1 62",
        )

    def test_user_text_wake_envelope(self):
        env = WAKE.format(
            agent="bt approve case-1 abcd1234", human="thanks &lt;3"
        )
        self.assertEqual(
            prompt_commands.user_text(env), "thanks <3"
        )

    def test_user_text_no_human_trigger_is_empty(self):
        env = WAKE.format(
            agent="bt approve case-1 abcd1234", human="ok"
        ).replace(' trigger="true"', "")
        self.assertEqual(prompt_commands.user_text(env), "")


if __name__ == "__main__":
    unittest.main()
