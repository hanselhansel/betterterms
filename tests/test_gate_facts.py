"""Structural fact amounts and the stricter review tier (decision
0010): hard-block floor rules read a fact's ``amount`` and ``period``
fields only, never its text; the review tier flags every spelled
number word, decimal or separator-joined digit form, non-isolated
digit token, currency or scale word or abbreviation, and every fact
whose text states a number its ``amount`` does not carry."""

import time
import unittest

from bt_helpers import (
    BRIEF_PAY,
    BtTestCase,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import render, yaml

LIMITS = "outside your limits; escalate to the user"


class FactAmountCase(BtTestCase):
    def make_case(self, direction="pay", floor=1200, plan=None):
        case_id, case_dir = new_case(self.home, direction=direction)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, direction=direction),
            plan=plan_for(direction, floor) if plan is None else plan,
            floor=floor,
        )
        return case_id

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

    def plan_with_fact(self, fact, **extra):
        return dict(plan_for("pay", 1200), facts=[fact], **extra)


class StructuralFactTest(FactAmountCase):
    def test_fact_amount_equal_to_floor_blocks(self):
        # The review probe: "Basic,1200 dollars a year" with amount
        # 1200 against a 1200 floor hard-blocks, on send or approved.
        plan = self.plan_with_fact(
            {"id": "f1", "text": "Basic,1200 dollars a year",
             "source": "x", "amount": 1200}
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:f1}")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn(LIMITS, out["reasons"])
        self.assertIsNone(out["rendered"])
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:f1}"), approved=True
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["reasons"], [LIMITS])

    def test_fact_null_amount_stating_money_needs_approval(self):
        # Same fact text with no structured amount: never a hard
        # block, always routed to the user.
        plan = self.plan_with_fact(
            {"id": "f1", "text": "Basic,1200 dollars a year",
             "source": "x"}
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:f1}")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertIn("structured amount", " ".join(out["reasons"]))

    def test_fact_text_without_numbers_and_null_amount_passes(self):
        # A number-free fact with no amount is plain user data.
        plan = self.plan_with_fact(
            {"id": "f1", "text": "they cancelled last week",
             "source": "x"}
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="note: {fact:f1}")
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("they cancelled last week", out["rendered"])

    def test_fact_amount_worse_than_floor_blocks_in_agreeing_context(self):
        # A structured fact amount worse than the floor blocks on any
        # action but send, where quoting a bad price is allowed.
        plan = self.plan_with_fact(
            {"id": "f1", "text": "they first quoted a steep price",
             "source": "x", "amount": 1500}
        )
        case_id = self.make_case(plan=plan)
        for action in ("pay", "accept", "sign", "cancel", "dispute"):
            with self.subTest(action=action):
                draft = send_draft(
                    action=action,
                    offer=1100 if action in ("pay", "accept", "sign")
                    else None,
                    template="their ask was {fact:f1}",
                )
                kw = {"approved": True}
                if action == "accept":
                    kw["inbound"] = {"offer": 1100, "text": "x",
                                     "amounts": []}
                proc, out = self.gate(case_id, draft, **kw)
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["reasons"], [LIMITS])
        proc, out = self.gate(
            case_id,
            send_draft(template="their ask was {fact:f1}"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 0, out)

    def test_fact_amount_reads_in_its_own_period(self):
        # floor 1200/month: a fact amount of 14400/year converts to
        # the floor's period and equals it: block.
        plan = dict(
            self.plan_with_fact(
                {"id": "f1", "text": "yearly quote on file",
                 "source": "x", "amount": 14400, "period": "year"}
            ),
            floor_period="month",
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:f1}"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["reasons"], [LIMITS])

    def test_fact_bad_period_is_a_broken_plan(self):
        plan = self.plan_with_fact(
            {"id": "f1", "text": "quoted weekly", "source": "x",
             "amount": 100, "period": "weekly"}
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:f1}")
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("period", out["error"])


class StricterReviewTest(FactAmountCase):
    def review(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        return out

    def test_spelled_number_forms_need_approval(self):
        case_id = self.make_case()
        for template in (
            "a twelve hundred",
            "an eleven hundred",
            "how about twelve fifty",
            "I have two options for you",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("number word", " ".join(out["reasons"]))

    def test_digit_within_two_tokens_of_a_number_word(self):
        case_id = self.make_case()
        for template in ("call it 12 fifty", "quote 12 of fifty items"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_scale_abbreviations_need_approval(self):
        # "5 mil" flags the digit next to the abbreviation; a bare
        # "k", "m", "mil" or "thou" flags on its own word.
        case_id = self.make_case()
        for template in ("about 5 mil", "plan k is third",
                         "option m below", "a mil more",
                         "worth a thou"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("scale", " ".join(out["reasons"]))

    def test_scale_abbrev_after_placeholder_needs_approval(self):
        # The review probe: "{offer} k" reads as a scaled amount.
        case_id = self.make_case()
        out = self.review(
            case_id, send_draft(template="I can do {offer} k today")
        )
        self.assertIn("scale", " ".join(out["reasons"]))

    def test_decimals_need_approval(self):
        case_id = self.make_case()
        for template in ("rate is 12.50", "rate 90.5 today",
                         "build 3.11 here"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_action_list_or_mapping_blocks_not_crashes(self):
        # The review probe: a non-string action used to die as an
        # unexpected TypeError (exit 2); it is a plain block (exit 1).
        case_id = self.make_case()
        for action in (["send"], {"send": True}, 2.5, None):
            with self.subTest(action=action):
                proc, out = self.gate(
                    case_id, send_draft(action=action, template="hi")
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["result"], "block")
                self.assertIn("not one of", " ".join(out["reasons"]))

    def test_render_stops_resolving_past_64kb(self):
        # Fact expansion stops at the size cap: a placeholder after
        # the fact that crosses it is never resolved.
        big = "word " * 14000  # ~70 KB once expanded
        plan = dict(
            plan_for("pay", 1200),
            facts=[{"id": "fb", "text": big, "source": "x"}],
        )
        find = render.render(
            "{fact:fb} then {nope}", None, "once", plan, "once", []
        )
        self.assertTrue(find.oversized)
        self.assertIsNone(find.text)
        self.assertFalse(any("nope" in e for e in find.errors))

    def test_64kb_fact_expansion_under_one_second(self):
        # The review probe: a fact just under the cap renders and
        # scans in well under a second.
        text = ",123" * 16000
        plan = dict(
            plan_for("pay", 1200),
            facts=[{"id": "fb", "text": text, "source": "x"}],
        )
        case_id = self.make_case(plan=plan)
        start = time.monotonic()
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:fb}")
        )
        elapsed = time.monotonic() - start
        self.assertEqual(proc.returncode, 3, out)
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
