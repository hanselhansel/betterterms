"""Structured-amounts gate: placeholder rendering and the review tier
for money-shaped literal text, including unicode bypass probes."""

import time
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


class RenderTest(BtTestCase):
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

    def blocked(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        return out


class PlaceholderRenderTest(RenderTest):
    def test_plan_placeholders_render_values(self):
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(
                template="target {target}; annual {option:annual}; "
                "step {ladder:1}"
            ),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            out["rendered"],
            "target $1,000; annual $950; step $1,000",
        )

    def test_fact_placeholder_auto_claims(self):
        # {fact:f1} adds f1 to claims, so the draft need not list it.
        # The fact text carries a price, so the review tier flags it.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:f1}"),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertEqual(
            out["rendered"], "see competitor charges $89 per month"
        )

    def test_placeholder_error_table(self):
        case_id = self.make_case()
        rows = [
            ("hi {nope}", "unknown placeholder {nope}"),
            ("hi {floor}", "unknown placeholder {floor}"),
            ("hi {offer:x}", "unknown placeholder {offer:x}"),
            ("hi {option:weekly}", "{option:weekly}"),
            ("hi {ladder:9}", "{ladder:9}"),
            ("hi {ladder:x}", "{ladder:x}"),
            ("hi {fact:f9}", "{fact:f9}"),
            ("hi {quote:0}", "{quote:0}"),
            ("hi {quote:2}", "{quote:2}"),
        ]
        for template, fragment in rows:
            with self.subTest(template=template):
                out = self.blocked(case_id, send_draft(template=template))
                self.assertIn(fragment, " ".join(out["reasons"]))

    def test_nonascii_placeholder_index_blocks_not_crashes(self):
        # Superscript and Arabic-Indic digits pass str.isdigit but are
        # not valid indexes; they must block, never crash or exit 2.
        case_id = self.make_case()
        for template in (
            "hi {ladder:¹}",
            "hi {ladder:٢}",
            "hi {quote:¹}",
        ):
            with self.subTest(template=template):
                out = self.blocked(case_id, send_draft(template=template))
                self.assertIn("{", " ".join(out["reasons"]))

    def test_offer_placeholder_with_null_offer_blocks(self):
        case_id = self.make_case()
        out = self.blocked(
            case_id, send_draft(offer=None, template="pay {offer}")
        )
        self.assertIn("{offer}", " ".join(out["reasons"]))

    def test_target_placeholder_with_null_target_blocks(self):
        case_id = self.make_case(plan={**PLAN_BILLS, "target": None})
        out = self.blocked(case_id, send_draft(template="aim {target}"))
        self.assertIn("{target}", " ".join(out["reasons"]))

    def test_quote_out_of_range_and_non_numeric(self):
        case_id = self.make_case()
        out = self.blocked(
            case_id, send_draft(template="you said {quote:2}"),
            inbound=inbound_msg(text="x", amounts=[89]),
        )
        self.assertIn("{quote:2}", " ".join(out["reasons"]))
        out = self.blocked(
            case_id, send_draft(template="you said {quote:1}"),
            inbound=inbound_msg(text="x", amounts=["soon"]),
        )
        self.assertIn("not a number", " ".join(out["reasons"]))

    def test_rendered_output_is_exact_send_text(self):
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(
                offer=85, period="month",
                template="we are at {offer}; your {quote:1} is steep",
            ),
            inbound=inbound_msg(text="we charge $140", amounts=[140]),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            out["rendered"],
            "we are at $85/month; your $140 is steep",
        )


class ReviewTierTest(RenderTest):
    """Money-shaped text outside placeholders no longer blocks: it
    routes the draft to the user as needs_approval with plain-word
    reasons. Only placeholder output carries amounts silently."""

    def review(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertIsNotNone(out["rendered"])
        return out

    def test_currency_signs_and_codes_need_approval(self):
        # Currency signs are off-allowlist characters; codes and words
        # are whole-token list matches.
        case_id = self.make_case()
        for template in (
            "it costs €100",
            "about £100",
            "around ¥1000",
            "S$100 flat",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "unusual characters", " ".join(out["reasons"])
                )
        for template in (
            "call it USD 100",
            "1200 EUR flat",
            "call it 12 usd",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("currency", " ".join(out["reasons"]))

    def test_currency_and_scale_words_need_approval(self):
        case_id = self.make_case()
        for template in (
            "100 dollars flat",
            "a few bucks more",
            "it is in euros",
            "fifty pounds",
            "a grand total",
            "ten yen",
            "about 1.2k",
            "about 1.2 k",
            "1.5 thousand",
            "a bn market",
            "it cost 5 mm",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertEqual(out["result"], "needs_approval")

    def test_digit_runs_need_approval(self):
        case_id = self.make_case()
        for template in (
            "order 1200 today",
            "about 100 units",
            "call 555 now",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_grouped_digit_runs_need_approval(self):
        # Group separators split tokens on the alphanumeric tokenizer,
        # and the tail token is a 3+ digit run. A real decimal like
        # 90.5 splits into small integers and passes.
        case_id = self.make_case()
        for template in (
            "it reads 1.200",
            "the cap is 1 200",
            "code 1'200",
            "call 90,500",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_unicode_digit_probes_need_approval(self):
        case_id = self.make_case()
        for template in (
            "see ¹²⁰⁰ now",     # superscript digits
            "see ١٢٣ today",    # arabic-indic digits
            "see １２００ today",  # fullwidth digits
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertEqual(out["result"], "needs_approval")

    def test_number_word_runs_need_approval(self):
        case_id = self.make_case()
        for template in (
            "one two zero zero is the code",
            "twelve fifty sounds right",
            "twenty one days is fine",
            "twelve hundred",
            "two million",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertEqual(out["result"], "needs_approval")

    def test_agreement_and_commitment_words_need_approval(self):
        case_id = self.make_case()
        for template in (
            "deal, we are set",
            "I agree to that",
            "I accept your terms",
            "that works for me",
            "happy to pay it",
            "I will pay 90",
            "go ahead with it",
            "please charge the card",
            "please process it today",
            "sign me up for it",
            "please cancel my account",
            "please confirm this",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "commitment", " ".join(out["reasons"])
                )

    def test_review_reasons_carry_no_numbers(self):
        case_id = self.make_case(
            floor=89.99, plan=plan_for("pay", 89.99, target=80)
        )
        out = self.review(
            case_id, send_draft(offer=80, template="pay USD 1200 now")
        )
        for reason in out["reasons"]:
            self.assertNotRegex(reason, r"\d")

    def test_allowed_small_forms_pass(self):
        case_id = self.make_case()
        for template in (
            "I have two options for you",
            "renewal in 12 months",
            "see you October 3",
            "see you October 15, 2026",
            "due 15 October 2026",
            "only 3 left in stock",
            "section 90 covers this",
            "we met in 96",
        ):
            with self.subTest(template=template):
                proc, out = self.gate(
                    case_id, send_draft(template=template)
                )
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(out["result"], "pass")

    def test_floor_8999_seven_days_is_not_a_review_item(self):
        # Owner decision: a sub-100 floor must not turn "7 days" into a
        # review item. Small integers pass unless they equal the
        # floor's integer part.
        case_id = self.make_case(
            floor=89.99, plan=plan_for("pay", 89.99, target=80)
        )
        proc, out = self.gate(
            case_id, send_draft(offer=80, template="reply within 7 days")
        )
        self.assertEqual(proc.returncode, 0, out)
        out = self.review(
            case_id, send_draft(offer=80, template="room 89 works")
        )
        self.assertEqual(out["result"], "needs_approval")

    def test_small_int_equal_to_sub100_floor_needs_approval(self):
        case_id = self.make_case(floor=50, plan=plan_for("pay", 50, target=40))
        out = self.review(
            case_id, send_draft(offer=45, template="meet in room 50")
        )
        self.assertEqual(out["result"], "needs_approval")

    def test_small_int_below_sub100_floor_passes(self):
        # floor 96: the standalone 8 no longer trips anything; only the
        # floor's integer value itself is protected below 100.
        case_id = self.make_case(floor=96, plan=plan_for("pay", 96, target=80))
        proc, out = self.gate(
            case_id, send_draft(offer=90, template="only 8 seats left")
        )
        self.assertEqual(proc.returncode, 0, out)

    def test_phone_digits_and_facts_need_approval(self):
        case_id = self.make_case(
            floor=85.50, plan=plan_for("pay", 85.50, target=80)
        )
        out = self.review(
            case_id, send_draft(offer=80, template="code 85 is mine")
        )
        self.assertEqual(out["result"], "needs_approval")
        out = self.review(
            case_id, send_draft(offer=80, template="call 800-555-0199")
        )
        self.assertIn("a number", " ".join(out["reasons"]))
        # The same digits inside a fact are fact text: still reviewed.
        plan = dict(
            plan_for("pay", 85.50, target=80),
            facts=[{"id": "f7", "text": "support line 800-555-0199",
                    "source": "x"}],
        )
        case_id = self.make_case(floor=85.50, plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=80, template="ring {fact:f7} tomorrow"),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("800-555-0199", out["rendered"])

    def test_64kb_template_under_one_second(self):
        case_id = self.make_case()
        template = "word " * 13000  # 65000 bytes, under the 64 KB cap
        start = time.monotonic()
        proc, out = self.gate(case_id, send_draft(template=template))
        elapsed = time.monotonic() - start
        self.assertEqual(proc.returncode, 0, out)
        self.assertLess(elapsed, 1.0)

    def test_rendered_over_64kb_blocks_before_scanning(self):
        # The cap applies to the rendered message, including fact
        # expansion, not the template.
        big = "word " * 14000  # ~70 KB once rendered
        plan = dict(
            plan_for("pay", 1200),
            facts=[{"id": "fbig", "text": big, "source": "x"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="note {fact:fbig}"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("too large", " ".join(out["reasons"]))


if __name__ == "__main__":
    unittest.main()
