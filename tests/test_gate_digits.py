"""0010 amendment review probes: any ASCII digit in the free text or
in a rendered fact's text routes to the user ("numbers in the
message"), number words match as substrings of letter runs, a
rendered offer whose digits equal the floor's digits routes as
"amount matches your limit's digits", and numeric ``never_disclose``
items compare against rendered placeholder values. Every probe here
must end needs_approval or block, never a pass."""

import time
import unittest

from bt_helpers import (
    BRIEF_PAY,
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


class AmendmentCase(BtTestCase):
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

    def review(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertIsNotNone(out["rendered"])
        return out

    def passed(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")
        return out


class AnyDigitRoutesTest(AmendmentCase):
    # Value: protects=0010 amendment "numbers in the message": every
    #   ASCII digit in the free text routes, the old small-integer and
    #   month-date exceptions are gone; fails_when=_small_number,
    #   _is_year or _date_parts comes back, or the digit scan runs on
    #   tokens instead of the raw masked text; seam=the probes below
    #   each slipped through one of the three old bypasses.
    def test_review_probes_with_digits_never_pass(self):
        case_id = self.make_case()
        for template in (
            "over 12 may not",
            "June - 1950",
            "see you October 3",
            "see you October 15, 2026",
            "due 15 October 2026",
            "renewal in 12 months",
            "only 3 left in stock",
            "section 90 covers this",
            "we met in 96",
            "reply within 7 days",
            "room 89 works",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("numbers", " ".join(out["reasons"]))

    def test_bare_month_name_still_passes(self):
        # Month names are ordinary words; it was the adjacent digits
        # that needed the exception, and the exception is gone.
        case_id = self.make_case()
        self.passed(case_id, send_draft(template="see you in October"))

    def test_digits_in_fact_text_need_approval(self):
        plan = dict(
            plan_for("pay", 1200),
            facts=[{"id": "fd", "text": "quoted on page 7",
                    "source": "x"}],
        )
        case_id = self.make_case(plan=plan)
        out = self.review(case_id, send_draft(template="see {fact:fd}"))
        self.assertIn("numbers", " ".join(out["reasons"]))

    def test_offer_plus_free_text_digits_need_approval(self):
        case_id = self.make_case()
        for template in ("{offer} and 50 cents", "{offer}, plus 50"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("numbers", " ".join(out["reasons"]))
        out = self.review(
            case_id, send_draft(template="{offer} and 50 cents")
        )
        self.assertIn("currency", " ".join(out["reasons"]))

    def test_long_digit_token_needs_approval_under_one_second(self):
        # A token past Python's int() digit limit used to die as an
        # unexpected ValueError. Review does no digit parsing now, so
        # any length is a plain match.
        case_id = self.make_case()
        template = "code " + "9" * 5000 + " end"
        start = time.monotonic()
        proc, out = self.gate(case_id, send_draft(template=template))
        elapsed = time.monotonic() - start
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertLess(elapsed, 1.0)


class NumberWordSubstringTest(AmendmentCase):
    # Value: protects=0010 amendment: number words match inside letter
    #   runs so glued forms flag; fails_when=the scan goes back to
    #   whole-token matching and "twelvehundred" passes; seam=glued
    #   forms were the review probe.
    def test_glued_number_forms_need_approval(self):
        case_id = self.make_case()
        for template in (
            "how about twelvehundred",
            "the price is fiftyish",
            "twentyone days",
            "fiftyfive flat",
            "the total was threehundred",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("number word", " ".join(out["reasons"]))

    def test_common_english_exceptions_pass(self):
        # Whole-word exceptions for ordinary words that contain a
        # number word as a substring.
        case_id = self.make_case()
        for template in (
            "how often does it renew",
            "the tone is professional",
            "money is not the issue",
            "a stone wall outside",
            "someone else handles it",
            "we are done",
            "they are gone",
            "none of it",
            "an honest answer",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))

    def test_exceptions_are_whole_word_only(self):
        # "oftener" is not the listed "often"; "stoned" is not "stone".
        case_id = self.make_case()
        for template in ("oftener than not", "a stoned wall"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("number word", " ".join(out["reasons"]))


class WordListAdditionsTest(AmendmentCase):
    # Value: protects=0010 amendment list additions; fails_when=the new
    #   currency words or commitment forms are dropped; seam="cancel"
    #   alone (not "cancel my") and bare "take it" were the probes.
    def test_new_currency_words_need_approval(self):
        case_id = self.make_case()
        for template in (
            "a few pesos more",
            "the won amount",
            "a rupee less",
            "a real offer",
            "three hundred yuan",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("currency", " ".join(out["reasons"]))

    def test_new_commitment_forms_need_approval(self):
        case_id = self.make_case()
        for template in (
            "take it or leave it",
            "take it at {quote:1}",
            "i'll take it",
            "we'll take the deal",
            "let's do it",
            "you have a deal",
            "count me in",
            "sold",
            "cancel the subscription",
            "please cancel my account",
        ):
            with self.subTest(template=template):
                out = self.review(
                    case_id,
                    send_draft(template=template),
                    inbound=inbound_msg(text="x", amounts=[1100]),
                )
                self.assertIn("commitment", " ".join(out["reasons"]))

    def test_cancelled_is_not_cancel(self):
        # Commitment words match whole tokens: the past-tense verb is
        # a different token and stays clean.
        case_id = self.make_case()
        self.passed(
            case_id, send_draft(template="they cancelled last week")
        )


class FloorDigitsTest(AmendmentCase):
    # Value: protects=0010 amendment "amount matches your limit's
    #   digits": an offer that repeats the floor's digits in a period
    #   that is not the floor's routes, never passes; fails_when=the
    #   check reads only the converted value (1200/year converts to
    #   100/month and slips through); seam=the 1200/year against a
    #   1200/month floor probe.
    def month_case(self, floor=1200):
        return self.make_case(
            plan=dict(plan_for("pay", floor), floor_period="month")
        )

    def test_offer_with_floor_digits_in_other_period_needs_approval(self):
        case_id = self.month_case()
        out = self.review(
            case_id,
            send_draft(offer=1200, period="year",
                       template="I can do {offer} prepaid"),
        )
        self.assertIn("limit's digits", " ".join(out["reasons"]))
        proc, out = self.gate(
            case_id,
            send_draft(offer=1200, period="year",
                       template="I can do {offer} prepaid"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "I can do $1,200/year prepaid")

    def test_same_period_floor_offer_keeps_at_limit_reason(self):
        case_id = self.month_case()
        out = self.review(
            case_id,
            send_draft(offer=1200, period="month",
                       template="my best is {offer}"),
        )
        self.assertIn("offer is at your limit", out["reasons"])
        self.assertNotIn("limit's digits", " ".join(out["reasons"]))

    def test_offer_without_floor_digits_passes(self):
        case_id = self.month_case()
        self.passed(
            case_id,
            send_draft(offer=1250, period="year",
                       template="I can do {offer} prepaid"),
        )

    def test_accept_sign_pay_offer_same_digits_exempt(self):
        # Agreeing actions may restate a price the counterparty named;
        # an in-band offer that shares the floor's digits does not
        # route on the digits check.
        case_id = self.month_case()
        for action in ("accept", "sign", "pay"):
            with self.subTest(action=action):
                kw = {}
                if action == "accept":
                    kw["inbound"] = inbound_msg(offer=1200, text="x")
                    kw["inbound"]["period"] = "year"
                draft = send_draft(
                    action=action, offer=1200, period="year",
                    template="let us close",
                )
                proc, out = self.gate(case_id, draft, **kw)
                self.assertEqual(proc.returncode, 3, out)
                self.assertNotIn(
                    "limit's digits", " ".join(out["reasons"])
                )
                proc, out = self.gate(
                    case_id, draft, approved=True, **kw
                )
                self.assertEqual(proc.returncode, 0, out)

    def test_quote_with_floor_digits_blocks(self):
        # A non-offer value equal to the floor's digits is already a
        # hard block, which is stricter than the approval route.
        case_id = self.month_case()
        proc, out = self.gate(
            case_id,
            send_draft(template="you quoted {quote:1}"),
            inbound=inbound_msg(text="x", amounts=[1200]),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["reasons"], [LIMITS])


class NeverDiscloseValuesTest(AmendmentCase):
    # Value: protects=0010 amendment: numeric never_disclose items
    #   compare against rendered placeholder values, not only the free
    #   text; fails_when=the masked scan hides "$1,100" behind the
    #   sentinel so the item never matches; seam=the offer is exactly
    #   the listed number.
    def test_numeric_item_matches_rendered_offer(self):
        case_id = self.make_case(
            brief={"never_disclose": ["1100"]}
        )
        out = self.review(
            case_id,
            send_draft(offer=1100, template="my offer is {offer}"),
        )
        self.assertIn("never-disclose", " ".join(out["reasons"]))

    def test_numeric_item_matches_other_rendered_values(self):
        case_id = self.make_case(
            brief={"never_disclose": ["950"]}
        )
        out = self.review(
            case_id,
            send_draft(template="the deal is {option:annual}"),
        )
        self.assertIn("never-disclose", " ".join(out["reasons"]))

    def test_numeric_item_still_matches_whole_text_numbers(self):
        # Digit runs fused across separators compare as digit strings:
        # "42" hits "42" and "1,200" hits "1 200", but not "420".
        case_id = self.make_case(brief={"never_disclose": ["42"]})
        out = self.review(
            case_id, send_draft(template="the code is 42")
        )
        self.assertIn("never-disclose", " ".join(out["reasons"]))
        out = self.review(
            case_id, send_draft(template="the code is 420")
        )
        self.assertNotIn("never-disclose", " ".join(out["reasons"]))

    def test_numeric_item_does_not_match_other_values(self):
        case_id = self.make_case(brief={"never_disclose": ["999"]})
        self.passed(
            case_id,
            send_draft(offer=1100, template="my offer is {offer}"),
        )


class RealisticDraftTest(AmendmentCase):
    # Value: protects=0010 amendment: ordinary negotiation English
    #   with no digits still passes; fails_when=the digit or
    #   letter-run rules get so broad that a normal draft routes;
    #   seam=none.
    def test_clean_english_draft_passes(self):
        case_id = self.make_case()
        out = self.passed(
            case_id,
            send_draft(
                template="Following up on our chat about the renewal. "
                "Could you look at the pricing on the premium plan? "
                "If there is room to improve the rate, I would "
                "appreciate it. Happy to jump on a call this week."
            ),
        )
        self.assertIn("Following up", out["rendered"])


if __name__ == "__main__":
    unittest.main()
