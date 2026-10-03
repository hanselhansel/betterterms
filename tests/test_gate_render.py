"""Structured-amounts gate: placeholder rendering and the free-text
money ban, including the review's unicode bypass probes."""

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
        case_id = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:f1}"),
        )
        self.assertEqual(proc.returncode, 0, out)
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


class FreeTextScanTest(RenderTest):
    """Every amount-shaped thing in free text blocks; only placeholders
    may carry money."""

    def test_currency_symbols_and_codes_block(self):
        case_id = self.make_case()
        for template in (
            "pay $100 now",
            "it costs €100",
            "about £100",
            "around ¥1000",
            "S$100 flat",
            "call it USD 100",
            "1200 EUR flat",
        ):
            with self.subTest(template=template):
                out = self.blocked(case_id, send_draft(template=template))
                self.assertIn(
                    "free text contains a currency symbol or code",
                    out["reasons"],
                )

    def test_currency_and_scale_words_block(self):
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
            "twelve hundred",
            "1.5 thousand",
            "two million",
            "a bn market",
            "it cost 5 mm",
        ):
            with self.subTest(template=template):
                out = self.blocked(case_id, send_draft(template=template))
                self.assertEqual(out["result"], "block")

    def test_digit_runs_block(self):
        case_id = self.make_case()
        for template in (
            "order 1200 today",
            "about 100 units",
            "call 555 now",
        ):
            with self.subTest(template=template):
                out = self.blocked(case_id, send_draft(template=template))
                self.assertIn(
                    "free text contains a number", out["reasons"]
                )

    def test_grouped_digit_runs_block(self):
        case_id = self.make_case()
        for template in (
            "pay 1,200 please",
            "it reads 1.200",
            "the cap is 1 200",
            "code 1'200",
            "rate 90.5 today",
            "build 3.11 here",
        ):
            with self.subTest(template=template):
                out = self.blocked(case_id, send_draft(template=template))
                self.assertEqual(out["result"], "block")

    def test_zero_width_and_unicode_digit_probes(self):
        case_id = self.make_case()
        probes = [
            "cap is 12\u200b00",
            "cap is 12\u200c00",
            "cap is 12\ufeff00",
            "pay ¹²⁰⁰ now",
            "see ١٢٣ today",
            "see １２００ today",
        ]
        for template in probes:
            with self.subTest(template=template):
                out = self.blocked(case_id, send_draft(template=template))
                self.assertEqual(out["result"], "block")

    def test_three_consecutive_number_words_block(self):
        case_id = self.make_case()
        out = self.blocked(
            case_id, send_draft(template="one two zero zero is the code")
        )
        self.assertEqual(out["result"], "block")

    def test_allowed_small_forms_pass(self):
        case_id = self.make_case()
        for template in (
            "I have two options for you",
            "twenty one days is fine",
            "renewal in 12 months",
            "see you October 3",
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

    def test_small_int_equal_to_floor_blocks(self):
        case_id = self.make_case(floor=50, plan=plan_for("pay", 50, target=40))
        out = self.blocked(
            case_id, send_draft(offer=45, template="meet in room 50")
        )
        self.assertEqual(out["result"], "block")

    def test_small_int_equal_to_floor_twelfths_blocks(self):
        # floor 96 -> 96 / 12 = 8: the standalone 8 leaks the floor's
        # twelfth just as surely as 96 itself would.
        case_id = self.make_case(floor=96, plan=plan_for("pay", 96, target=80))
        out = self.blocked(
            case_id, send_draft(offer=90, template="only 8 seats left")
        )
        self.assertEqual(out["result"], "block")

    def test_cents_floor_versus_phone_digits(self):
        case_id = self.make_case(
            floor=85.50, plan=plan_for("pay", 85.50, target=80)
        )
        # The floor's integer part in free text still discloses it.
        out = self.blocked(
            case_id, send_draft(offer=80, template="code 85 is mine")
        )
        self.assertEqual(out["result"], "block")
        # A phone-style digit run blocks as a number, not as the floor.
        out = self.blocked(
            case_id, send_draft(offer=80, template="call 800-555-0199")
        )
        self.assertIn("free text contains a number", out["reasons"])
        # The same digits inside a fact render verbatim and pass.
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
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("800-555-0199", out["rendered"])

    def test_64kb_template_under_one_second(self):
        case_id = self.make_case()
        template = "word " * 13000  # 65000 bytes, under the 64 KB cap
        start = time.monotonic()
        proc, out = self.gate(case_id, send_draft(template=template))
        elapsed = time.monotonic() - start
        self.assertEqual(proc.returncode, 0, out)
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
