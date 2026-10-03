"""Structured-amounts gate: agreement wording, quote-vs-floor rules,
period conversion, and template shape checks."""

import unittest

from bt_helpers import (
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


class ProbeTest(BtTestCase):
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

    def blocked(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        return out


class AgreementWordTest(ProbeTest):
    def test_agreement_words_make_send_needs_approval(self):
        case_id = self.make_case()
        templates = [
            "deal, we are set",
            "agreed then",
            "I accept your terms",
            "happy to accept your price",
            "that works for me",
            "sounds good, let's do it",
            "go ahead and charge the card",
            "sign me up for it",
            "please cancel my account",
        ]
        for template in templates:
            with self.subTest(template=template):
                proc, out = self.gate(case_id, send_draft(template=template))
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")
                proc, out = self.gate(
                    case_id, send_draft(template=template), approved=True
                )
                self.assertEqual(proc.returncode, 0, out)

    def test_i_accept_charge_my_card_probe(self):
        # Review probe: agreement wording inside a send may not slip
        # through as a plain message.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(template="I accept. Please charge my card."),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")

    def test_agreement_check_is_send_only(self):
        # A cancel action may say the words; it is irreversible and
        # already needs approval either way.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(action="cancel", offer=None,
                       template="please cancel my account"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 0, out)


class QuoteAndPeriodTest(ProbeTest):
    def test_quote_worse_than_floor_only_for_send(self):
        case_id = self.make_case()
        inbound = inbound_msg(text="we charge $1,300", amounts=[1300])
        proc, out = self.gate(
            case_id, send_draft(template="your {quote:1} is too high"),
            inbound=inbound,
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "your $1,300 is too high")
        for action in ("accept", "pay", "sign", "cancel", "dispute"):
            with self.subTest(action=action):
                draft = send_draft(
                    action=action,
                    offer=1100 if action in ("accept", "pay", "sign") else None,
                    template="noting your {quote:1}",
                )
                out = self.blocked(
                    case_id, draft, approved=True, inbound=inbound
                )
                self.assertIn(LIMITS, out["reasons"])

    def test_offer_at_floor_converted_from_yearly(self):
        # plan period month, floor 1200/month: a $14,400/year offer is
        # the floor converted and inside the band, so it may render.
        plan = dict(PLAN_BILLS, period="month")
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=14400, period="year",
                       template="I can do {offer} prepaid"),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "I can do $14,400/year prepaid")
        proc, out = self.gate(
            case_id,
            send_draft(offer=15000, period="year",
                       template="I can do {offer} prepaid"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_rendered_plan_value_at_floor_blocks(self):
        # target == floor is inside the band for the plan check, but
        # rendering it shows the floor, so only the offer may.
        plan = dict(PLAN_BILLS, target=1200)
        case_id = self.make_case(plan=plan)
        out = self.blocked(
            case_id, send_draft(template="the ask is {target}")
        )
        self.assertIn(LIMITS, out["reasons"])

    def test_rendered_plan_value_worse_than_floor_blocks(self):
        # A yearly option of 15000 with a monthly floor of 1200 is
        # 1250/month: outside the band.
        plan = dict(
            PLAN_BILLS,
            period="month",
            options=[{"label": "annual", "value": 15000,
                      "period": "year", "terms": "prepay"}],
            facts=[],
        )
        case_id = self.make_case(plan=plan)
        out = self.blocked(
            case_id, send_draft(template="how about {option:annual}")
        )
        self.assertIn(LIMITS, out["reasons"])

    def test_quote_equal_floor_twelfth_blocks(self):
        # floor 1200/month; quoting a yearly 14400 == floor * 12 leaks.
        plan = dict(PLAN_BILLS, period="month")
        case_id = self.make_case(plan=plan)
        out = self.blocked(
            case_id, send_draft(template="you said {quote:1}"),
            inbound=inbound_msg(text="$14,400 a year", amounts=[14400]),
        )
        self.assertIn(LIMITS, out["reasons"])


class TemplateShapeTest(ProbeTest):
    def test_non_string_template_blocks(self):
        case_id = self.make_case()
        for bad in (["hi"], 42, {"x": 1}, True):
            with self.subTest(template=bad):
                out = self.blocked(case_id, send_draft(template=bad))
                self.assertIn("template must be a string", out["reasons"])

    def test_period_must_be_valid(self):
        case_id = self.make_case()
        out = self.blocked(case_id, send_draft(period="weekly"))
        self.assertIn("period must be once, month or year", out["reasons"])
        for period in ("once", "month", "year"):
            with self.subTest(period=period):
                proc, out = self.gate(
                    case_id, send_draft(offer=1100, period=period)
                )
                self.assertEqual(proc.returncode, 0, out)


if __name__ == "__main__":
    unittest.main()
