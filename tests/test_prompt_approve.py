"""The ``bt approve`` path of the UserPromptSubmit hook (spec 6.8):
the marker write, the wake-envelope split, the stale-hash refusal and
the runnable gate command the pass-through note names. Split from
test_prompt_commands.py under the 400-line cap; shared helpers live
there.
"""

import json
import os
import re
import shlex
import subprocess
import unittest

from bt_helpers import (
    BT,
    BRIEF_PAY,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
)
from btlib import yaml

from test_prompt_commands import (
    HookCase,
    WAKE,
    additional_context,
    hook_json,
    run_hook,
)


class ApproveCommandTest(HookCase):
    def test_wake_envelope_uses_human_trigger_only(self):
        # Review Focus 1: an earlier agent message quotes `bt approve`;
        # only the triggering human text counts, so nothing is
        # approved.
        case_dir = self.make_case()
        held_dir, h = self.hold(case_dir)
        envelope = WAKE.format(
            agent=f"bt approve case-1 {h[:8]}", human="thanks"
        )
        proc = run_hook(self.home, envelope)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertFalse((held_dir / f"{h}.approved").exists())

    def test_wake_envelope_human_approve(self):
        case_dir = self.make_case()
        held_dir, h = self.hold(case_dir)
        envelope = WAKE.format(
            agent="the draft is ready",
            human=f"bt approve case-1 {h[:8]}",
        )
        proc = run_hook(self.home, envelope)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((held_dir / f"{h}.approved").is_file())
        out = hook_json(proc)
        note = additional_context(out)
        # The note tells the agent to run the gate with --approved
        # once, then send the rendered text verbatim. The mod's send
        # check is gone (decision 0020), so the same instruction
        # applies with or without the mod loaded. The command is
        # runnable as printed: the resolved absolute bt.py path and
        # the case's draft path; no --inbound when no inbound exists.
        self.assertIn("approved", note)
        self.assertIn("bt.py gate", note)
        self.assertIn("--approved", note)
        self.assertIn("--draft", note)
        self.assertIn("verbatim", note)
        self.assertNotIn("--inbound", note)
        self.assertNotIn("send check", note)

    def test_approve_note_command_runs_once_on_real_btpy(self):
        # The emitted command is real: python3, the resolved absolute
        # bt.py path, the case id, --draft <case>/draft.yaml, --inbound
        # <case>/inbound.yaml when it exists, --approved. Run verbatim
        # against the real bt.py it passes exactly once; the marker
        # spends, so a second run holds the draft again.
        case_id, case_dir = new_case(self.home)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, autonomy=2),
            plan=plan_for("pay", 1200),
            floor=1200,
        )
        draft = send_draft(
            action="cancel", offer=None, template="please end my plan"
        )
        (case_dir / "draft.yaml").write_text(yaml.dump(draft))
        (case_dir / "inbound.yaml").write_text(
            yaml.dump({"offer": None, "text": "no", "amounts": []})
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft",
            str(case_dir / "draft.yaml"),
        )
        self.assertEqual(proc.returncode, 3, out)
        h = out["hash"]
        proc = run_hook(self.home, f"bt approve {case_id} {h[:8]}")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        note = additional_context(hook_json(proc))
        m = re.search(r"`(python3 [^`]+)`", note)
        self.assertIsNotNone(m, note)
        argv = shlex.split(m.group(1))
        self.assertEqual(argv[:3], ["python3", str(BT), "gate"])
        self.assertEqual(argv[3], case_id)
        for flag, path in (
            ("--draft", case_dir / "draft.yaml"),
            ("--inbound", case_dir / "inbound.yaml"),
        ):
            self.assertIn(flag, argv)
            self.assertEqual(argv[argv.index(flag) + 1], str(path))
        self.assertIn("--approved", argv)
        env = dict(os.environ, BETTERTERMS_HOME=str(self.home))
        first = subprocess.run(
            argv, capture_output=True, text=True, env=env, timeout=30
        )
        self.assertEqual(
            first.returncode, 0, first.stdout + first.stderr
        )
        self.assertEqual(json.loads(first.stdout)["result"], "pass")
        again = subprocess.run(
            argv, capture_output=True, text=True, env=env, timeout=30
        )
        self.assertEqual(again.returncode, 3, again.stdout)

    def test_approve_note_command_runs_once_with_space_in_home(self):
        # Every argv element is quoted when the command is printed:
        # with a BETTERTERMS_HOME containing a space, the note's
        # command still parses to the real paths, runs as printed and
        # spends the marker exactly once.
        home = self.tmp / "bt home"
        case_id, case_dir = new_case(home)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, autonomy=2),
            plan=plan_for("pay", 1200),
            floor=1200,
        )
        draft = send_draft(
            action="cancel", offer=None, template="please end my plan"
        )
        (case_dir / "draft.yaml").write_text(yaml.dump(draft))
        proc, out = run_bt_json(
            home, "gate", case_id, "--draft",
            str(case_dir / "draft.yaml"),
        )
        self.assertEqual(proc.returncode, 3, out)
        h = out["hash"]
        proc = run_hook(home, f"bt approve {case_id} {h[:8]}")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        note = additional_context(hook_json(proc))
        m = re.search(r"`(python3 [^`]+)`", note)
        self.assertIsNotNone(m, note)
        argv = shlex.split(m.group(1))
        self.assertEqual(
            argv[argv.index("--draft") + 1],
            str(case_dir / "draft.yaml"),
        )
        env = dict(os.environ, BETTERTERMS_HOME=str(home))
        first = subprocess.run(
            argv, capture_output=True, text=True, env=env, timeout=30
        )
        self.assertEqual(
            first.returncode, 0, first.stdout + first.stderr
        )
        self.assertEqual(json.loads(first.stdout)["result"], "pass")
        again = subprocess.run(
            argv, capture_output=True, text=True, env=env, timeout=30
        )
        self.assertEqual(again.returncode, 3, again.stdout)

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

    def test_approve_stale_hash_blocks(self):
        # gate.json names the draft the last gate verdict held; a
        # typed `bt approve` for a different held record is a stale
        # card: no marker is written and no note tells the model to
        # send.
        case_dir = self.make_case()
        held_dir, h = self.hold(case_dir)
        # A newer verdict held a different draft.
        self.hold(case_dir, rendered="a newer held draft")
        proc = run_hook(self.home, f"bt approve case-1 {h[:8]}")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("not the current held draft", out["reason"])
        self.assertNotIn("send", out["reason"].lower())
        self.assertFalse((held_dir / f"{h}.approved").exists())

    def test_approve_without_gate_json_blocks(self):
        # No recorded verdict, no approval: the hook cannot tell a
        # held record is current when gate.json is missing.
        case_dir = self.make_case()
        held_dir, h = self.hold(case_dir)
        (case_dir / "gate.json").unlink()
        proc = run_hook(self.home, f"bt approve case-1 {h[:8]}")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("not the current held draft", out["reason"])
        self.assertFalse((held_dir / f"{h}.approved").exists())


if __name__ == "__main__":
    unittest.main()
