"""Structural fact amounts and the stricter review tier (decision
0010): hard-block floor rules read a fact's ``amount`` and ``period``
fields only, never its text; the review tier flags every ASCII digit
in the free text or in a fact's rendered text, every spelled number
word inside a letter run, and every currency or scale word or
abbreviation."""

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

    def test_fact_null_amount_with_digits_needs_approval(self):
        # Same fact text with no structured amount routes to the user
        # on its digits. The glued ",1200" form is not a money parse,
        # so the rendered-text floor rule does not reach it; a spaced
        # "1,200" in fact text would hard-block (test_floor_in_text).
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
        self.assertIn("numbers", " ".join(out["reasons"]))

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

    # Generated by /ship coverage audit.
    # Value: protects=a fact id only listed in claims joins no floor
    #   comparison (decision 0010 A), while the same fact rendered does;
    #   fails_when=claims start feeding fact amounts into the floor
    #   rules, blocking in-band drafts that only cite a fact;
    #   why_new=existing claims tests cover unknown ids and rendered
    #   facts, never a valid unrendered claim; seam=none
    def test_claimed_but_unrendered_fact_amount_is_not_compared(self):
        for amount, action in ((1200, "send"), (1500, "pay")):
            with self.subTest(amount=amount, action=action):
                plan = self.plan_with_fact(
                    {"id": "f3", "text": "they quoted a price",
                     "source": "x", "amount": amount}
                )
                case_id = self.make_case(plan=plan)
                kw = {"approved": action != "send"}
                proc, out = self.gate(
                    case_id,
                    send_draft(action=action, template="as noted earlier",
                               claims=["f3"]),
                    **kw,
                )
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(out["rendered"], "as noted earlier")
                # Control: rendering the same fact reaches the rule.
                proc, out = self.gate(
                    case_id,
                    send_draft(action=action, template="noted {fact:f3}"),
                    **kw,
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(LIMITS, out["reasons"])

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
            case_id,
            send_draft(period="month", template="see {fact:f1}"),
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

    # Generated by /ship coverage audit (pass 2).
    # Value: protects=a fact amount that is set but not a usable number
    #   fails closed (0010 A: amount is a number or null), like target,
    #   ladder, option and quote values do;
    # fails_when=render treats a non-number or over-cap amount as absent,
    #   so an approved accept skips the fact floor rule and passes;
    # why_new=fact tests cover numeric and null amounts only; seam=none
    def test_fact_amount_not_a_number_fails_closed(self):
        for amount in ("lots", 5e12, True, [1500]):
            with self.subTest(amount=amount):
                plan = self.plan_with_fact(
                    {"id": "f1", "text": "they first quoted a steep price",
                     "source": "x", "amount": amount}
                )
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(
                    case_id,
                    send_draft(action="accept",
                               template="their ask was {fact:f1}"),
                    approved=True,
                    inbound={"offer": 1100, "text": "x", "amounts": []},
                )
                self.assertIn(proc.returncode, (1, 2), out)
                self.assertNotEqual(out.get("result"), "pass", out)


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
            "an eleven thousand",
            "how about twelve fifty",
            "I have two options for you",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("number word", " ".join(out["reasons"]))

    def test_digits_and_spelled_amounts_need_approval(self):
        case_id = self.make_case()
        for template in ("call it 12 fifty", "quote 12 of fifty items"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("numbers", " ".join(out["reasons"]))

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
                self.assertIn("numbers", " ".join(out["reasons"]))

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
