"""Step-2 review fixes: a sentinel the template cannot type, NUL and
control characters off the allowlist, separator-joined digit groups
read as one number, number-word runs across punctuation, number words
equal to the floor, and 64 KB scans that stay linear."""

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


class ReviewFixCase(BtTestCase):
    def make_case(self, direction="pay", floor=1200, plan=None, brief=None):
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
        return out

    def passed(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")
        return out


class SentinelTest(ReviewFixCase):
    def test_nul_and_control_characters_need_approval(self):
        case_id = self.make_case()
        controls = ["\x00", "\x07", "\x1b", "\x7f"] + [
            chr(i) for i in range(1, 32) if i != 10
        ]
        for ch in controls:
            template = "Hi " + ch + " there"
            with self.subTest(ch=ch.encode("unicode_escape")):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "unusual characters", " ".join(out["reasons"])
                )

    def test_sentinel_character_in_template_needs_approval(self):
        # The mask sentinel is a private-use character the gate rejects
        # when the template itself carries it: otherwise a typed
        # sentinel could pretend to be placeholder output.
        case_id = self.make_case()
        for template in (
            "pay " + render._MASK + " flat",
            render._MASK,
        ):
            with self.subTest(template=template.encode("unicode_escape")):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "unusual characters", " ".join(out["reasons"])
                )

    def test_sentinel_character_in_fact_text_needs_approval(self):
        plan = dict(
            plan_for("pay", 1200),
            facts=[
                {"id": "fs", "text": "x" + render._MASK + "y",
                 "source": "x"},
            ],
        )
        case_id = self.make_case(plan=plan)
        out = self.review(case_id, send_draft(template="see {fact:fs}"))
        self.assertIn("unusual characters", " ".join(out["reasons"]))


class JoinedDigitsTest(ReviewFixCase):
    def test_separator_joined_groups_need_approval(self):
        # Digit groups fused by separators evaluate as the whole joined
        # number, never as separate small tokens.
        case_id = self.make_case()
        for template in (
            "My ceiling is 1,050 per month",
            "the price is 1,099",
            "the cap reads 1.099",
            "the cap reads 1 050",
            "the code reads 12 50",
            "the figure 1,234,567 flat",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_grouped_number_never_passes_at_its_floor(self):
        # floor 1050: "1,050" restates the limit as joined digits. It
        # routes to the user, never a silent pass.
        case_id = self.make_case(floor=1050)
        out = self.review(
            case_id,
            send_draft(offer=1040,
                       template="My ceiling is 1,050 per month"),
        )
        self.assertIn("a number", " ".join(out["reasons"]))

    def test_leading_zero_digit_tokens_need_approval(self):
        case_id = self.make_case()
        for template in ("room 007 it is", "code 050 works"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_decimals_and_adjacent_digits_need_approval(self):
        # Decision 0010: decimals and adjacent digit tokens are
        # number-shaped now; only month-name dates still pass.
        case_id = self.make_case()
        for template in (
            "rate 90.5 today",
            "build 3.11 here",
            "rooms 3 4 are free",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_month_name_dates_still_pass(self):
        case_id = self.make_case()
        for template in (
            "meet October 15, 2026",
            "due 15 October 2026",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))


class NumberWordRunTest(ReviewFixCase):
    def test_punctuation_and_newlines_do_not_break_runs(self):
        case_id = self.make_case()
        for template in (
            "eleven\nninety\nnine",
            "one, two, three",
            "twelve. fifty",
            "one - two",
            "twenty-one days",
        ):
            with self.subTest(template=template.encode("unicode_escape")):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("number word", " ".join(out["reasons"]))

    def test_number_word_equal_to_floor_needs_approval(self):
        case_id = self.make_case(
            floor=50, plan=plan_for("pay", 50, target=40)
        )
        out = self.review(
            case_id, send_draft(offer=45, template="about fifty flat")
        )
        self.assertIn("matching your limit", " ".join(out["reasons"]))

    def test_number_word_below_floor_needs_approval(self):
        # Decision 0010: any spelled number word routes to the user,
        # matching the floor or not.
        case_id = self.make_case(
            floor=50, plan=plan_for("pay", 50, target=40)
        )
        out = self.review(
            case_id, send_draft(offer=45, template="about forty flat")
        )
        self.assertIn("number word", " ".join(out["reasons"]))


class HostileScanTimingTest(ReviewFixCase):
    def test_gate_never_disclose_64kb_under_one_second(self):
        # A comma-digit run made the suffixed-amount regex quadratic;
        # the never-disclose whole-number scan must stay linear.
        case_id = self.make_case(brief={"never_disclose": ["1200"]})
        template = ",123" * 16000  # 64 KB of comma-digit run
        start = time.monotonic()
        proc, out = self.gate(case_id, send_draft(template=template))
        elapsed = time.monotonic() - start
        self.assertEqual(proc.returncode, 3, out)
        self.assertLess(elapsed, 1.0)

    def test_gate_fact_text_64kb_under_one_second(self):
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


class FactExpansionTest(ReviewFixCase):
    def test_oversized_render_never_materializes(self):
        # The 64 KB check is computed from piece lengths before the
        # rendered string is built: an oversized render leaves
        # ``text`` unset instead of joining megabytes.
        big = "word " * 14000  # ~70 KB once expanded
        plan = dict(
            plan_for("pay", 1200),
            facts=[{"id": "fb", "text": big, "source": "x"}],
        )
        find = render.render(
            "note {fact:fb}", None, "once", plan, "once", []
        )
        self.assertTrue(find.oversized)
        self.assertIsNone(find.text)

    def test_repeated_fact_oversized_blocks(self):
        big = "word " * 8000  # ~40 KB; two expansions cross 64 KB
        plan = dict(
            plan_for("pay", 1200),
            facts=[{"id": "fb", "text": big, "source": "x"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="{fact:fb} {fact:fb}")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("too large", " ".join(out["reasons"]))
        self.assertIsNone(out["rendered"])


if __name__ == "__main__":
    unittest.main()
