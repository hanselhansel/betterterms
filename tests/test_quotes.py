"""Spec 4.4: quoting a counterparty's price.

A ``{quote:n}`` restates what the counterparty wrote, so its amount is
never the agent's offer: the worse-than-floor and unconvertible-period
checks never reach a quote on any action. A string entry in the
inbound ``amounts`` list renders their words verbatim, and because
inbound.yaml is written by the agent the verbatim text is reviewed
like the agent's own: digits, commitment wording and every other
review rule apply, and a listed ``never_disclose`` term inside a
quote is a hard block. A rendered quote equal to the floor still
blocks, and every rule outside quotes is unchanged.
"""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    PriceCase,
    inbound_msg,
    plan_for,
    send_draft,
)

LIMITS = "outside your limits; escalate to the user"


class QuoteRuleCase(PriceCase):
    def quote_case(self, floor=60, brief=None):
        return self.make_case(
            floor=floor,
            plan=plan_for("pay", floor, target=50),
            brief=brief,
        )


class QuoteNotAnOfferTest(QuoteRuleCase):
    def test_quote_above_floor_passes_floor_check(self):
        # pay floor 60; the counterparty's own 89 sits above it, yet a
        # cancel draft may quote it back: quoting is not offering.
        case_id = self.quote_case()
        proc, out = self.gate(
            case_id,
            {"action": "cancel", "offer": None, "period": "once",
             "template": "You charged {quote:1}. Please cancel.",
             "claims": []},
            inbound=inbound_msg(text="we bill 89", amounts=[89]),
        )
        self.assertNotEqual(out["result"], "block", out)
        self.assertFalse(
            any("limit" in r for r in out["reasons"]),
            out["reasons"],
        )

    def test_quote_off_send_never_meets_floor_check(self):
        # The same exemption holds on a non-send action: a dispute
        # quoting a worse-than-floor amount never blocks on the floor.
        case_id = self.quote_case()
        proc, out = self.gate(
            case_id,
            {"action": "dispute", "offer": None, "period": "once",
             "template": "You billed {quote:1}; fix it.",
             "claims": []},
            inbound=inbound_msg(text="we bill 89", amounts=[89]),
        )
        self.assertNotEqual(out["result"], "block", out)
        self.assertFalse(
            any("limit" in r for r in out["reasons"]),
            out["reasons"],
        )

    def test_offer_above_floor_still_blocks(self):
        # The same 89 as the draft's own offer stays a hard block:
        # only quoted amounts are exempt.
        case_id = self.quote_case()
        proc, out = self.gate(
            case_id,
            send_draft(offer=89, template="I can pay {offer}."),
            inbound=inbound_msg(text="we bill 89", amounts=[89]),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_quote_equal_to_floor_still_blocks(self):
        # Restating the walk-away number is a leak whoever wrote it:
        # a quote equal to the floor still hard blocks.
        case_id = self.quote_case()
        proc, out = self.gate(
            case_id,
            send_draft(offer=50, template="you said {quote:1}"),
            inbound=inbound_msg(text="flat", amounts=[60]),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])


class VerbatimQuoteTest(QuoteRuleCase):
    def test_quote_renders_inbound_text_verbatim(self):
        # A string amounts entry is the counterparty's words as they
        # wrote them, not a reformatted price. A clean string passes;
        # one carrying digits still renders untouched in the text the
        # user approves.
        case_id = self.quote_case()
        proc, out = self.gate(
            case_id,
            send_draft(offer=50, template="you said {quote:1}"),
            inbound=inbound_msg(text="as discussed",
                                amounts=["as discussed"]),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("as discussed", out["rendered"])
        proc, out = self.gate(
            case_id,
            send_draft(offer=50, template="you said {quote:1}"),
            inbound=inbound_msg(text="CHF 90 flat",
                                amounts=["CHF 90 flat"]),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("CHF 90 flat", out["rendered"])

    def test_string_quote_digits_need_approval(self):
        # inbound.yaml is written by the agent, so a verbatim string
        # is agent-authored text: digits inside it route to the user
        # like digits anywhere else, at autonomy 3 and 4.
        for autonomy in (3, 4):
            case_id = self.quote_case(brief={"autonomy": autonomy})
            proc, out = self.gate(
                case_id,
                send_draft(offer=50, template="you said {quote:1}"),
                inbound=inbound_msg(text="the rate is 75",
                                    amounts=["the rate is 75"]),
            )
            with self.subTest(autonomy=autonomy):
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")
                self.assertIn(
                    "numbers in the message", out["reasons"])

    def test_string_quote_commitment_words_need_approval(self):
        # Same layer, different rule: commitment wording inside a
        # verbatim string is the agent's to vouch for too.
        for autonomy in (3, 4):
            case_id = self.quote_case(brief={"autonomy": autonomy})
            proc, out = self.gate(
                case_id,
                send_draft(offer=50, template="you said {quote:1}"),
                inbound=inbound_msg(text="yes, i agree",
                                    amounts=["yes, i agree"]),
            )
            with self.subTest(autonomy=autonomy):
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")
                self.assertIn(
                    "commitment", " ".join(out["reasons"]))

    def test_quote_checked_against_never_disclose(self):
        # A verbatim quote is still their words: a listed term inside
        # it is a hard block, not a review item.
        case_id = self.quote_case(brief={"never_disclose": ["CHF 90"]})
        proc, out = self.gate(
            case_id,
            send_draft(offer=50, template="you said {quote:1}"),
            inbound=inbound_msg(text="CHF 90 flat", amounts=["CHF 90"]),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("never-disclose", " ".join(out["reasons"]))

    def test_numeric_quote_still_formats_as_price(self):
        # A numeric entry keeps the old rendering (money_text output).
        case_id = self.quote_case()
        proc, out = self.gate(
            case_id,
            send_draft(offer=50, template="you said {quote:1}"),
            inbound=inbound_msg(text="we bill 89", amounts=[89]),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("$89", out["rendered"])


if __name__ == "__main__":
    unittest.main()
