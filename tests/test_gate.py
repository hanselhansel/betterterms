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

    def gate(self, case_id, draft, approved=False):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if approved:
            args.append("--approved")
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
