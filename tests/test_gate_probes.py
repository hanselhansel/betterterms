"""Structured-amounts gate: agreement wording, quote-vs-floor rules,
period conversion, and template shape checks."""

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
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        if approved:
            args = approve_held(self.home, case_id, args)
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
    def test_quote_worse_than_floor_never_meets_floor_check(self):
        # Spec 4.4: a quote restates the counterparty's own number, so
        # the worse-than-floor check never reaches it on any action.
        case_id = self.make_case()
        inbound = inbound_msg(
            offer=1100, text="we charge $1,300", amounts=[1300]
        )
        proc, out = self.gate(
            case_id, send_draft(template="your {quote:1} is too high"),
            inbound=inbound,
        )
        # The inbound offer sits in the near_floor band, so the turn
        # is stopped and the draft held as a proposal (decision 0021);
        # the quote still never meets the worse-than-floor check.
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["reasons"], [
            "the counterparty's message needs your review",
        ])
        self.assertEqual(out["rendered"], "your $1,300 is too high")
        for action in ("accept", "pay", "sign", "cancel", "dispute"):
            with self.subTest(action=action):
                draft = send_draft(
                    action=action,
                    offer=1100 if action in ("accept", "pay", "sign") else None,
                    template="noting your {quote:1}",
                )
                proc, out = self.gate(
                    case_id, draft, approved=True, inbound=inbound
                )
                self.assertEqual(proc.returncode, 0, out)
                self.assertNotIn(LIMITS, out["reasons"])

    def test_offer_at_floor_converted_from_yearly(self):
        # plan period month, floor 1200/month: a $14,400/year offer is
        # the floor converted. Inside the band, but on send it reveals
        # the walk-away number, so it routes to the user.
        plan = dict(PLAN_BILLS, period="month")
        case_id = self.make_case(plan=plan)
        draft = send_draft(offer=14400, period="year",
                           template="I can do {offer} prepaid")
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])
        self.assertNotIn("limit", " ".join(out["reasons"]))
        self.assertEqual(out["rendered"], "I can do $14,400/year prepaid")
        proc, out = self.gate(case_id, draft, approved=True)
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

    def test_quote_equal_floor_twelfth_needs_approval(self):
        # floor 1200/month; quoting a yearly 14400 is the floor * 12.
        # A converted match routes to the user, it does not block.
        plan = dict(PLAN_BILLS, period="month")
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="you said {quote:1}"),
            inbound=inbound_msg(text="$14,400 a year", amounts=[14400]),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])
        self.assertNotIn(
            "converted limit", " ".join(out["reasons"])
        )
        proc, out = self.gate(
            case_id, send_draft(template="you said {quote:1}"),
            approved=True,
            inbound=inbound_msg(text="$14,400 a year", amounts=[14400]),
        )
        self.assertEqual(proc.returncode, 0, out)


class Pass3ProbeTest(ProbeTest):
    """The pass-3 probe list from the gate-scope decision: every probe
    is either a hard block (structural) or needs_approval (textual),
    never a silent pass."""

    def review(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertIsNotNone(out["rendered"])
        return out

    def test_digit_adjacent_to_offer_output(self):
        # "{offer}0" merges a literal digit into the rendered amount:
        # "$1,100" plus a stray 0 reads as another number.
        case_id = self.make_case()
        out = self.review(
            case_id, send_draft(template="I can do {offer}0 today")
        )
        self.assertIn("numbers", " ".join(out["reasons"]))

    def test_empty_fact_joiners(self):
        # A fact whose text is only invisible joiners still adds
        # invisible characters to the rendered message.
        case_id = self.make_case(
            plan={
                "target": 1000, "options": [], "ladder": [],
                "facts": [{"id": "fz", "text": "‌‌", "source": "x"}],
            }
        )
        out = self.review(
            case_id, send_draft(template="see {fact:fz} soon")
        )
        self.assertEqual(out["result"], "needs_approval")

    def test_invisible_chars_inside_digits_and_accept(self):
        # Invisible and format characters are off the character
        # allowlist, so every one of these routes to the user.
        case_id = self.make_case()
        for template in (
            "pay 12­00 now",
            "pay 12⁣00 now",
            "pay 12‎00 now",
            "I ac­cept that",
            "I acc⁣ept that",
            "I ac‎cept that",
        ):
            with self.subTest(template=template.encode("unicode_escape")):
                out = self.review(
                    case_id, send_draft(template=template)
                )
                self.assertIn(
                    "unusual characters", " ".join(out["reasons"])
                )

    def test_fact_with_accept_and_price_needs_approval(self):
        case_id = self.make_case(
            plan={
                "target": 1000, "options": [], "ladder": [],
                "facts": [
                    {"id": "fx", "text": "I accept their $1,500 offer",
                     "source": "x"},
                ],
            }
        )
        out = self.review(
            case_id, send_draft(template="they wrote {fact:fx}")
        )
        self.assertEqual(out["result"], "needs_approval")

    def test_twelve_fifty_needs_approval(self):
        case_id = self.make_case()
        out = self.review(
            case_id, send_draft(template="how about twelve fifty")
        )
        self.assertEqual(out["result"], "needs_approval")

    def test_lowercase_currency_code_needs_approval(self):
        case_id = self.make_case()
        out = self.review(
            case_id, send_draft(template="call it 12 usd flat")
        )
        self.assertIn("currency", " ".join(out["reasons"]))

    def test_happy_to_pay_quote_process_it(self):
        case_id = self.make_case()
        out = self.review(
            case_id,
            send_draft(
                template="Happy to pay {quote:1}, please process it"
            ),
            inbound=inbound_msg(text="we charge $1,100",
                                amounts=[1100]),
        )
        self.assertIn("commitment", " ".join(out["reasons"]))

    def test_bonus_fee_options_floor_rules(self):
        # Bonus and fee options are exempt from the worse-than-floor
        # comparison but may not render a value equal to the floor.
        plan = {
            "target": 1000,
            "options": [
                {"label": "signup", "value": 1200, "kind": "bonus"},
                {"label": "shipping", "value": 1500, "kind": "fee"},
                {"label": "annual", "value": 950, "kind": "price"},
            ],
            "ladder": [], "facts": [],
        }
        case_id = self.make_case(plan=plan)
        out = self.blocked(
            case_id, send_draft(template="keep the {option:signup}")
        )
        self.assertIn(LIMITS, out["reasons"])
        # A fee above the floor renders masked, so the send passes.
        proc, out = self.gate(
            case_id, send_draft(template="the {option:shipping} stays")
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("$1,500", out["rendered"])

    def test_once_offer_against_month_floor(self):
        # Floor declared monthly; a once offer cannot convert, so the
        # raw values are never compared: every send routes to the
        # user, however large the raw number reads.
        plan = dict(PLAN_BILLS, period="month")
        case_id = self.make_case(plan=plan)
        for offer in (14400, 1100):
            with self.subTest(offer=offer):
                draft = send_draft(
                    offer=offer, period="once",
                    template="I can do {offer} prepaid",
                )
                proc, out = self.gate(case_id, draft)
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["reasons"], [REVIEW])
                proc, out = self.gate(case_id, draft, approved=True)
                self.assertEqual(proc.returncode, 0, out)

    def test_month_offer_against_once_floor(self):
        # Floor declared once; a monthly offer cannot convert, so the
        # draft routes to the user.
        case_id = self.make_case()
        draft = send_draft(
            offer=1100, period="month",
            template="I can do {offer}",
        )
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])
        self.assertNotIn(
            "period differs", " ".join(out["reasons"])
        )
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 0, out)


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
                if period == "once":
                    self.assertEqual(proc.returncode, 0, out)
                else:
                    # A recurring offer against the once floor
                    # cannot convert, so it routes to the user.
                    self.assertEqual(proc.returncode, 3, out)
                    self.assertIn(REVIEW, out["reasons"])
                    self.assertNotIn(
                        "period differs", " ".join(out["reasons"])
                    )


if __name__ == "__main__":
    unittest.main()
