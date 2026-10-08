import unittest

from bt_helpers import (
    approve_held,
    BRIEF_PAY,
    PLAN_BILLS,
    BtTestCase,
    inbound_msg,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import yaml

LIMITS = "outside your limits; escalate to the user"
REVIEW = "a value in this draft needs your review"


class GateTest(BtTestCase):
    def make_case(self, direction="pay", floor=1200, brief=None, plan=None):
        case_id, case_dir = new_case(self.home, direction=direction)
        b = dict(BRIEF_PAY, direction=direction)
        if brief:
            b.update(brief)
        write_case_files(
            case_dir,
            brief=b,
            plan=plan_for(direction, floor) if plan is None else plan,
            floor=floor,
        )
        return case_id, case_dir

    def gate(self, case_id, draft, approved=False, inbound=None):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        if approved:
            args = approve_held(self.home, case_id, args)
        return run_bt_json(self.home, *args)

    def test_offer_above_floor_blocks_pay(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(case_id, send_draft(offer=1250))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn(LIMITS, out["reasons"])

    def test_offer_below_floor_passes_pay(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(template="could you do better on price")
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")
        self.assertEqual(out["reasons"], [])
        self.assertEqual(out["rendered"], "could you do better on price")

    def test_offer_at_floor_needs_approval_and_renders(self):
        # An offer at the floor reveals the walk-away on send, so it
        # routes to the user; an explicit yes still renders it.
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(offer=1200, template="my best is {offer}")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])
        self.assertNotIn("limit", " ".join(out["reasons"]))
        self.assertEqual(out["rendered"], "my best is $1,200")
        proc, out = self.gate(
            case_id,
            send_draft(offer=1200, template="my best is {offer}"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "my best is $1,200")

    def test_offer_with_month_period_renders(self):
        # A monthly offer on a once floor cannot convert: held for
        # the user, and the rendered text is still exact.
        case_id, _ = self.make_case(floor=1200)
        draft = send_draft(
            offer=85, period="month",
            template="I can do {offer} on the new plan",
        )
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])
        self.assertNotIn("period differs", " ".join(out["reasons"]))
        self.assertEqual(
            out["rendered"], "I can do $85/month on the new plan"
        )
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            out["rendered"], "I can do $85/month on the new plan"
        )

    def test_gate_direction_receive(self):
        case_id, _ = self.make_case(direction="receive", floor=150000)
        proc, out = self.gate(
            case_id,
            send_draft(offer=140000, template="thanks for the offer"),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn(LIMITS, out["reasons"])

    def test_direction_receive_offer_above_floor_passes(self):
        case_id, _ = self.make_case(direction="receive", floor=150000)
        proc, out = self.gate(
            case_id,
            send_draft(offer=160000, template="excited to discuss"),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")

    def test_claim_not_in_facts_blocks(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(template="as shown before", claims=["f9"])
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn("f9", " ".join(out["reasons"]))

    def test_free_text_money_needs_approval(self):
        # Money-shaped literal text is review tier: never a silent
        # pass. Amounts still go through placeholders.
        case_id, _ = self.make_case(floor=1200)
        for template in ("I can pay $89", "call it USD 100",
                         "the fee is 500"):
            with self.subTest(template=template):
                proc, out = self.gate(case_id, send_draft(template=template))
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")

    def test_fact_placeholder_renders_verbatim_and_claims(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(template="remember: {fact:f1}, so sharpen the pencil"),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(
            out["rendered"],
            "remember: competitor charges $89 per month, "
            "so sharpen the pencil",
        )

    def test_quote_placeholder_needs_inbound_amounts(self):
        case_id, _ = self.make_case(floor=1200)
        draft = send_draft(template="you quoted {quote:1} last week")
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 1, out)
        proc, out = self.gate(
            case_id, draft,
            inbound=inbound_msg(text="we can do $89",
                                amounts=[89]),
        )
        # No inbound offer means the real score is unknown: held for
        # the user (decision 0021), and the quote still rendered.
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["reasons"], [
            "the counterparty's message needs your review",
        ])
        self.assertEqual(out["rendered"], "you quoted $89 last week")

    def test_quote_equal_to_floor_blocks_even_on_send(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(template="your own {quote:1} works for me"),
            inbound=inbound_msg(offer=1200, text="fine, $1,200 it is",
                                amounts=[1200]),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn(LIMITS, out["reasons"])

    def test_inbound_missing_file_errors(self):
        case_id, _ = self.make_case(floor=1200)
        path = write_draft(self.tmp, send_draft(offer=1, template="x"))
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path),
            "--inbound", str(self.tmp / "nope.yaml"),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_gate_without_floor_blocks(self):
        case_id, _ = self.make_case(floor=None)
        proc, out = self.gate(case_id, send_draft(template="hello"))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn(LIMITS, out["reasons"])

    def test_never_disclose_blocks(self):
        # A listed term with letters is a hard block, never a
        # review item or a coincidence.
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(template="my account is ACCT-7788")
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["result"], "block")
        self.assertIn("never-disclose", " ".join(out["reasons"]))

    def test_offer_restated_in_free_text_needs_approval(self):
        # Bypass probe: a bare offer in free text, not {offer}.
        # Commitment wording routes it to the user.
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(offer=90, template="I will pay 90")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")

    def test_unknown_case_errors(self):
        path = write_draft(self.tmp, send_draft(offer=1, template="x"))
        proc, out = run_bt_json(
            self.home, "gate", "nope-20000101-0000", "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_text_key_rejected(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            {"action": "send", "offer": 1100, "text": "hi", "claims": []},
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("use template, not text", out["reasons"])

    def test_unknown_draft_key_blocks(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(template="hi", note="see below")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("unknown draft keys: note", out["reasons"])

    def test_missing_template_blocks(self):
        case_id, _ = self.make_case(floor=1200)
        draft = send_draft()
        del draft["template"]
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 1, out)

    def test_rendered_is_null_on_block(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(case_id, send_draft(offer=1300))
        self.assertEqual(proc.returncode, 1, out)
        self.assertIsNone(out["rendered"])

    def test_send_offer_at_floor_needs_approval_both_directions(self):
        # A send offer equal to the floor hands the counterparty the
        # walk-away: needs_approval both ways, number-free reason.
        for direction, floor in (("pay", 1200), ("receive", 150000)):
            with self.subTest(direction=direction):
                case_id, _ = self.make_case(
                    direction=direction, floor=floor
                )
                draft = send_draft(offer=floor, template="counter")
                proc, out = self.gate(case_id, draft)
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")
                self.assertIn(REVIEW, out["reasons"])
                self.assertFalse(
                    any(any(c.isdigit() for c in r)
                        for r in out["reasons"])
                )
                proc, out = self.gate(case_id, draft, approved=True)
                self.assertEqual(proc.returncode, 0, out)

    def test_send_offer_at_floor_after_period_conversion(self):
        # floor 1200/month: converted offers on it hold too.
        plan = dict(plan_for("pay", 1200), period="month")
        case_id, _ = self.make_case(floor=1200, plan=plan)
        for offer, period in ((14400, "year"), (1200, "month")):
            with self.subTest(offer=offer, period=period):
                proc, out = self.gate(
                    case_id,
                    send_draft(offer=offer, period=period,
                               template="counter"),
                )
                self.assertEqual(proc.returncode, 3, out)
                self.assertIn(REVIEW, out["reasons"])
                self.assertNotIn(
                    "limit", " ".join(out["reasons"])
                )

    def test_send_offer_within_floor_tolerance_needs_approval(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(offer=1200.004, template="counter")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])

    def test_yaml11_booleans_in_lists_do_not_crash(self):
        # YAML 1.1 loads yes/no/on/off as booleans. A bool where a list
        # was expected must produce a gate verdict, never a traceback.
        case_id, case_dir = self.make_case(floor=1200)
        (case_dir / "brief.yaml").write_text(
            "pack: bills\nmode: act\ndirection: pay\nautonomy: 2\n"
            "never_disclose: yes\n"
        )
        draft_path = self.tmp / "draft.yaml"
        draft_path.write_text(
            "action: send\noffer: 1100\ntemplate: a counter offer\n"
            "claims: yes\n"
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(draft_path)
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(out["result"], "block")
        self.assertIn("not in plan facts", " ".join(out["reasons"]))


if __name__ == "__main__":
    unittest.main()
