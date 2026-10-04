"""The UserPromptSubmit settings hook: typed ``bt ...`` commands
(spec 6.8).

Only the user's own text counts: inside a Projects wake envelope that
is the ``<message>`` with ``trigger="true"`` and ``from="human"``;
anywhere else the whole prompt. ``bt floor`` writes the walk-away
through ``bt.py case set-floor`` on stdin and blocks the prompt, so
the number never reaches the model or the hook's own stdout. The
other verbs write through bt.py and pass with a note.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from bt_helpers import REPO, BtTestCase
from btlib import yaml

sys.path.insert(0, str(REPO / "hooks"))
import prompt_commands  # noqa: E402

HOOK = REPO / "hooks" / "prompt_commands.py"

WAKE = (
    '<wake reason="thread-reply">'
    '<message from="agent">{agent}</message>'
    '<message from="human" trigger="true">{human}</message>'
    "</wake>"
)


def run_hook(home, prompt):
    event = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s-1",
        "transcript_path": "/tmp/bt-test-sess/transcript.jsonl",
        "cwd": "/tmp",
        "prompt": prompt,
    }
    env = dict(
        os.environ,
        BETTERTERMS_HOME=str(home),
        CLAUDE_PLUGIN_ROOT=str(REPO),
    )
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def hook_json(proc):
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"hook did not print JSON\nstdout: {proc.stdout}\n"
            f"stderr: {proc.stderr}"
        )


def additional_context(out):
    return out["hookSpecificOutput"]["additionalContext"]


class HookCase(BtTestCase):
    def make_case(self, cid="case-1"):
        d = self.home / "cases" / cid
        d.mkdir(parents=True)
        return d

    def hold(self, case_dir, h):
        held = case_dir / "held"
        held.mkdir(exist_ok=True)
        (held / f"{h}.yaml").write_text(
            yaml.dump(
                {
                    "hash": h,
                    "rendered": "a held draft",
                    "reasons": ["cancel needs your yes"],
                    "held_at": "2026-10-04T00:00:00+00:00",
                }
            )
        )
        return held


class FloorCommandTest(HookCase):
    def test_plain_prompt_floor_blocked_and_saved(self):
        d = self.make_case()
        proc = run_hook(self.home, "bt floor case-1 62")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertEqual((d / ".floor").read_text().strip(), "62.00")
        self.assertNotIn("62", proc.stdout)

    def test_bad_amount_message(self):
        d = self.make_case()
        proc = run_hook(self.home, "bt floor case-1 sixty")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("use a number", out["reason"])
        self.assertFalse((d / ".floor").exists())

    def test_unknown_case(self):
        proc = run_hook(self.home, "bt floor case-9 62")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("no case case-9", out["reason"])

    def test_amount_formats(self):
        d = self.make_case()
        for typed, stored in (
            ("$62", "62.00"),
            ("62.50", "62.50"),
            ("1,200", "1200.00"),
        ):
            with self.subTest(typed=typed):
                proc = run_hook(
                    self.home, f"bt floor case-1 {typed}"
                )
                out = hook_json(proc)
                self.assertEqual(out["decision"], "block")
                self.assertEqual(
                    (d / ".floor").read_text().strip(), stored
                )
        proc = run_hook(self.home, "bt floor case-1 62k")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("use a number", out["reason"])

    def test_floor_with_trailing_text_never_reaches_model(self):
        d = self.make_case()
        proc = run_hook(self.home, "bt floor case-1 62 please")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("62", proc.stdout)
        self.assertFalse((d / ".floor").exists())


class ApproveCommandTest(HookCase):
    HASH = "abcd1234" + "0" * 56

    def test_wake_envelope_uses_human_trigger_only(self):
        # Review Focus 1: an earlier agent message quotes `bt approve`;
        # only the triggering human text counts, so nothing is
        # approved.
        case_dir = self.make_case()
        held = self.hold(case_dir, self.HASH)
        envelope = WAKE.format(
            agent="bt approve case-1 abcd1234", human="thanks"
        )
        proc = run_hook(self.home, envelope)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertFalse((held / f"{self.HASH}.approved").exists())

    def test_wake_envelope_human_approve(self):
        case_dir = self.make_case()
        held = self.hold(case_dir, self.HASH)
        envelope = WAKE.format(
            agent="the draft is ready",
            human="bt approve case-1 abcd1234",
        )
        proc = run_hook(self.home, envelope)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((held / f"{self.HASH}.approved").is_file())
        out = hook_json(proc)
        note = additional_context(out)
        self.assertIn("approved", note)
        self.assertIn("same text", note)

    def test_approve_bad_hash_blocks(self):
        self.make_case()
        proc = run_hook(self.home, "bt approve case-1 xyz")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("hash", out["reason"])

    def test_approve_no_match_blocks(self):
        self.make_case()
        proc = run_hook(self.home, "bt approve case-1 abcd1234")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("no held draft", out["reason"])


class RejectAndTermsTest(HookCase):
    HASH = "beef5678" + "0" * 56

    def test_reject_removes_and_notes(self):
        case_dir = self.make_case()
        held = self.hold(case_dir, self.HASH)
        proc = run_hook(self.home, "bt reject case-1 beef5678")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((held / f"{self.HASH}.yaml").exists())
        self.assertIn(
            "rejected", (case_dir / "thread.md").read_text()
        )
        note = additional_context(hook_json(proc))
        self.assertIn("reject", note.lower())

    def test_terms_updates_plan_and_notes(self):
        case_dir = self.make_case()
        proc = run_hook(
            self.home,
            "bt terms case-1 target=60 alternative=50",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 60)
        self.assertEqual(plan["best_alternative"]["amount"], 50)
        note = additional_context(hook_json(proc))
        self.assertIn("terms", note)


class NonCommandTest(HookCase):
    def test_plain_text_passes_silently(self):
        proc = run_hook(self.home, "please lower my bill")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_malformed_bt_line_blocks_with_usage(self):
        proc = run_hook(self.home, "bt approve")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt approve", out["reason"])


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
