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

from bt_helpers import REPO, BtTestCase
from btlib import context as context_mod
from btlib import held as held_mod, yaml

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

    def hold(self, case_dir, rendered="a held draft"):
        # A real held record: the filename is the tuple hash, so the
        # fixture exercises the same integrity check bt.py applies.
        # gate.json goes with it: a held record only exists after a
        # gate verdict wrote one, and held approve refuses a hash
        # gate.json does not name.
        record = held_mod.make_record(
            "cancel", None, "once", "USD", rendered,
            context_mod.digest(None),
        )
        h = held_mod.draft_hash(record)
        held = case_dir / "held"
        held.mkdir(exist_ok=True)
        (held / f"{h}.yaml").write_text(
            yaml.dump(
                {
                    "hash": h,
                    **record,
                    "reasons": ["cancel needs your yes"],
                    "held_at": "2026-10-04T00:00:00+00:00",
                }
            )
        )
        (case_dir / "gate.json").write_text(
            json.dumps(
                {
                    "result": "needs_approval",
                    "reasons": ["cancel needs your yes"],
                    "rendered": rendered,
                    "hash": h,
                }
            )
        )
        return held, h


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

    def test_floor_lookalike_at_message_start_never_reaches_model(self):
        # A lookalike blocks only at the start of the trimmed text
        # (one leading backtick or slash allowed) and only when the
        # line still carries a digit: it claims to set the walk-away,
        # so the number never reaches the model.
        d = self.make_case()
        for prompt in (
            "`bt floor case-1 62`",
            "/bt floor case-1 62",
            "bt floor case-1 sixty two dollars 62",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                out = hook_json(proc)
                self.assertEqual(out["decision"], "block")
                self.assertNotIn("62", proc.stdout)
                self.assertFalse((d / ".floor").exists())

    def test_floor_near_miss_blocks_with_usage(self):
        self.make_case()
        proc = run_hook(self.home, "bt floor case-1")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt floor", out["reason"])


class RejectAndTermsTest(HookCase):
    def test_reject_removes_and_notes(self):
        case_dir = self.make_case()
        held_dir, h = self.hold(case_dir)
        proc = run_hook(self.home, f"bt reject case-1 {h[:8]}")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((held_dir / f"{h}.yaml").exists())
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

    def test_terms_target_key_only(self):
        # The terms widget sends only the keys the user filled.
        case_dir = self.make_case()
        proc = run_hook(self.home, "bt terms case-1 target=80")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 80)
        self.assertIsNone(plan.get("best_alternative"))
        self.assertIn("terms", additional_context(hook_json(proc)))

    def test_terms_alternative_key_only(self):
        case_dir = self.make_case()
        proc = run_hook(self.home, "bt terms case-1 alternative=55")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertIsNone(plan.get("target"))
        self.assertEqual(plan["best_alternative"]["amount"], 55)

    def test_terms_reversed_order(self):
        case_dir = self.make_case()
        proc = run_hook(
            self.home,
            "bt terms case-1 alternative=50 target=60",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 60)
        self.assertEqual(plan["best_alternative"]["amount"], 50)

    def _pay_case_with_floor(self, floor="70.00"):
        d = self.make_case()
        (d / "brief.yaml").write_text(yaml.dump({"direction": "pay"}))
        (d / ".floor").write_text(f"{floor}\n")
        return d

    def test_terms_past_walk_away_blocks_with_reason(self):
        # A refused set-terms blocks the prompt outright: the reason
        # reaches the user and no note ever reaches the model.
        case_dir = self._pay_case_with_floor()
        proc = run_hook(self.home, "bt terms case-1 target=100")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("wrong side of your walk-away", out["reason"])
        self.assertNotRegex(out["reason"], r"\d")
        # Nothing saved: the bare case dir still has no plan.yaml.
        self.assertFalse((case_dir / "plan.yaml").exists())

    def test_terms_inside_walk_away_saves_and_notes(self):
        case_dir = self._pay_case_with_floor()
        proc = run_hook(self.home, "bt terms case-1 target=60")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(
            "terms", additional_context(hook_json(proc))
        )
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 60)

    def test_floor_below_saved_target_blocks_with_reason(self):
        d = self._pay_case_with_floor()
        (d / ".floor").unlink()
        (d / "plan.yaml").write_text(yaml.dump({"target": 100}))
        proc = run_hook(self.home, "bt floor case-1 65")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("wrong side of your target", out["reason"])
        # The refusal reason never carries a number, like every
        # other floor-path block.
        self.assertNotRegex(out["reason"], r"\d")
        self.assertFalse((d / ".floor").exists())

    def test_terms_repeated_key_blocks(self):
        case_dir = self.make_case()
        proc = run_hook(
            self.home, "bt terms case-1 target=60 target=70"
        )
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt terms", out["reason"])
        self.assertFalse((case_dir / "plan.yaml").exists())

    def test_terms_unknown_key_blocks(self):
        # A terms-shaped line whose = pairs hold a key the grammar
        # does not know fails the parse, then still looks like a
        # terms attempt (it starts with `bt terms` and carries `=`).
        case_dir = self.make_case()
        proc = run_hook(self.home, "bt terms case-1 note=60")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt terms", out["reason"])
        self.assertFalse((case_dir / "plan.yaml").exists())


class NonCommandTest(HookCase):
    def test_plain_text_passes_silently(self):
        proc = run_hook(self.home, "please lower my bill")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_words_containing_bt_pass_silently(self):
        # The opener needs a token boundary: "debt terms" and
        # "doubt floor" carry no command, so they must not block.
        for prompt in (
            "renegotiate my debt terms",
            "I doubt floor prices drop",
            "the debtor floor debate continues",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), "")

    def test_malformed_bt_line_blocks_with_usage(self):
        proc = run_hook(
            self.home, "bt approve case-1 abcd1234 please"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("bt approve", out["reason"])

    def test_embedded_approve_is_prose_and_passes(self):
        # `bt approve` inside a sentence is not a command attempt: the
        # line passes through untouched and approves nothing.
        case_dir = self.make_case()
        held_dir, h = self.hold(case_dir)
        proc = run_hook(
            self.home, f"ok bt approve case-1 {h[:8]} thanks"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertFalse((held_dir / f"{h}.approved").exists())


if __name__ == "__main__":
    unittest.main()
