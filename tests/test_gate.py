import unittest

from bt_helpers import (
    BRIEF_PAY,
    PLAN_BILLS,
    BtTestCase,
    new_case,
    run_bt_json,
    write_case_files,
    write_draft,
)
from btlib import yaml


class GateTest(BtTestCase):
    def make_case(self, direction="pay", floor=1200, brief=None, plan=None):
        case_id, case_dir = new_case(self.home, direction=direction)
        b = dict(BRIEF_PAY, direction=direction)
        if brief:
            b.update(brief)
        write_case_files(
            case_dir,
            brief=b,
            plan=PLAN_BILLS if plan is None else plan,
            floor=floor,
        )
        return case_id, case_dir

    def gate(self, case_id, draft, approved=False, inbound=None):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if approved:
            args.append("--approved")
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        return run_bt_json(self.home, *args)

    def test_offer_above_floor_blocks_pay(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(case_id, {"action": "send", "offer": 1250, "text": "final", "claims": []})
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn("worse than floor", " ".join(out["reasons"]))

    def test_offer_below_floor_passes_pay(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 1100, "text": "could you do better on price", "claims": []},
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")
        self.assertEqual(out["reasons"], [])

    def test_gate_blocks_floor_variants(self):
        variants = [
            "my max is $1,200",
            "I can go up to 1.2k",
            "the number is 1200.00",
            "twelve hundred is my limit",
        ]
        for text in variants:
            with self.subTest(text=text):
                case_id, _ = self.make_case(floor=1200)
                proc, out = self.gate(
                    case_id, {"action": "send", "offer": 1100, "text": text, "claims": []}
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["result"], "block")
                self.assertIn("floor disclosed", " ".join(out["reasons"]))

    def test_gate_direction_receive(self):
        case_id, _ = self.make_case(direction="receive", floor=150000)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 140000, "text": "thanks for the offer", "claims": []},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn("worse than floor", " ".join(out["reasons"]))

    def test_direction_receive_offer_above_floor_passes(self):
        case_id, _ = self.make_case(direction="receive", floor=150000)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 160000, "text": "excited to discuss", "claims": []},
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")

    def test_irreversible_action_needs_approval(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {"action": "accept", "offer": 1100, "text": "sounds good", "claims": []},
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")

    def test_irreversible_action_approved_passes(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {"action": "accept", "offer": 1100, "text": "sounds good", "claims": []},
            approved=True,
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")

    def test_claim_not_in_facts_blocks(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 1100, "text": "as shown before", "claims": ["f9"]},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn("f9", " ".join(out["reasons"]))

    def test_untraced_number_blocks(self):
        case_id, _ = self.make_case(floor=1200, plan={**PLAN_BILLS, "facts": []})
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 1100, "text": "$89 at Competitor", "claims": []},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn("untraced number", " ".join(out["reasons"]))

    def test_traced_number_from_fact_passes(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {
                "action": "send",
                "offer": 1100,
                "text": "Competitor charges $89 per month",
                "claims": ["f1"],
            },
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")

    def test_yaml11_booleans_in_lists_do_not_crash(self):
        # YAML 1.1 loads yes/no/on/off as booleans. A bool where a list
        # was expected must produce a gate verdict, never a traceback.
        case_id, case_dir = self.make_case(floor=1200)
        (case_dir / "brief.yaml").write_text(
            "pack: bills\nmode: act\ndirection: pay\nnever_disclose: yes\n"
        )
        draft_path = self.tmp / "draft.yaml"
        draft_path.write_text(
            "action: send\noffer: 1100\ntext: a counter offer\nclaims: yes\n"
        )
        proc, out = run_bt_json(self.home, "gate", case_id, "--draft", str(draft_path))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(out["result"], "block")
        self.assertIn("not in plan facts", " ".join(out["reasons"]))

    def test_counterparty_amount_traced_only_with_inbound(self):
        # A draft quoting the counterparty's own $89 blocks as an
        # untraced number without --inbound and passes with it.
        plan = {**PLAN_BILLS, "facts": []}
        case_id, _ = self.make_case(floor=1200, plan=plan)
        draft = {
            "action": "send",
            "offer": 1100,
            "text": "as you said, $89 is competitive",
            "claims": [],
        }
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("untraced number", " ".join(out["reasons"]))
        proc, out = self.gate(
            case_id, draft,
            inbound={"offer": None, "text": "we can do $89 per month"},
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")

    def test_inbound_offer_amount_traced(self):
        plan = {**PLAN_BILLS, "facts": []}
        case_id, _ = self.make_case(floor=1200, plan=plan)
        proc, out = self.gate(
            case_id,
            {
                "action": "send",
                "offer": 1100,
                "text": "matching your $89 figure",
                "claims": [],
            },
            inbound={"offer": 89, "text": "attached is our quote"},
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")

    def test_inbound_does_not_unblock_floor_disclosure(self):
        # The floor stays blocked even when the counterparty stated it:
        # the floor-leak rule stands apart from untraced numbers.
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {
                "action": "send",
                "offer": 1100,
                "text": "your own $1,200 works for me",
                "claims": [],
            },
            inbound={"offer": 1200, "text": "fine, $1,200 it is"},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("floor disclosed", " ".join(out["reasons"]))

    def test_inbound_missing_file_errors(self):
        case_id, _ = self.make_case(floor=1200)
        path = write_draft(
            self.tmp, {"action": "send", "offer": 1, "text": "x", "claims": []}
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path),
            "--inbound", str(self.tmp / "nope.yaml"),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_gate_without_floor_blocks(self):
        case_id, _ = self.make_case(floor=None)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 1100, "text": "hello", "claims": []},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn("floor", " ".join(out["reasons"]))

    def test_never_disclose_blocks(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 1100, "text": "my account is ACCT-7788", "claims": []},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")

    def test_offer_amount_in_text_traced_to_offer(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 1100, "text": "I can pay $1,100 this month", "claims": []},
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")

    def test_unknown_case_errors(self):
        path = write_draft(self.tmp, {"action": "send", "offer": 1, "text": "x", "claims": []})
        proc, out = run_bt_json(self.home, "gate", "nope-20000101-0000", "--draft", str(path))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
