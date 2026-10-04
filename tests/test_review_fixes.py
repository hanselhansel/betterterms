"""Step-2 review fixes: a sentinel the template cannot type, NUL and
control characters off the allowlist, digits anywhere in the text
routing to the user, number-word runs across punctuation and inside
glued letter runs, scale words inside glued letter runs, and 64 KB
scans that stay linear."""

import time
import unittest
from unittest import mock

from bt_helpers import (
    approve_held,
    BRIEF_PAY,
    BtTestCase,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import render, review, wordlists, yaml


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
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        if approved:
            args = approve_held(self.home, case_id, args)
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
        # Every digit token routes on its own; separator-joined groups
        # can no longer split a number into passing small tokens.
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
                self.assertIn("numbers", " ".join(out["reasons"]))

    def test_grouped_number_never_passes_at_its_floor(self):
        # floor 1050: "1,050" restates the limit as joined digits; the
        # rendered-text rule now blocks it (test_floor_in_text.py).
        case_id = self.make_case(floor=1050)
        proc, out = self.gate(
            case_id,
            send_draft(offer=1040,
                       template="My ceiling is 1,050 per month"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("walk-away", " ".join(out["reasons"]))

    def test_leading_zero_digit_tokens_need_approval(self):
        case_id = self.make_case()
        for template in ("room 007 it is", "code 050 works"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("numbers", " ".join(out["reasons"]))

    def test_decimals_and_adjacent_digits_need_approval(self):
        # Decision 0010 amendment: every digit form routes; no date or
        # small-number exception remains.
        case_id = self.make_case()
        for template in (
            "rate 90.5 today",
            "build 3.11 here",
            "rooms 3 4 are free",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("numbers", " ".join(out["reasons"]))

    def test_month_name_dates_need_approval(self):
        # 0010 amendment: the month-name date exception is gone.
        case_id = self.make_case()
        for template in (
            "meet October 15, 2026",
            "due 15 October 2026",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("numbers", " ".join(out["reasons"]))


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

    def test_number_word_at_floor_blocks(self):
        # "fifty" spells out the 50 floor: the rendered-text rule
        # blocks the draft outright (test_floor_in_text.py).
        case_id = self.make_case(
            floor=50, plan=plan_for("pay", 50, target=40)
        )
        proc, out = self.gate(
            case_id, send_draft(offer=45, template="about fifty flat")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("walk-away", " ".join(out["reasons"]))

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

    def test_never_disclose_numeric_items_stay_set_linear(self):
        # Thousands of numeric never-disclose items each search the
        # fused digit groups and the rendered placeholder values:
        # linear scans per item are quadratic on a 64 KB input.
        # The groups are a set and the values a sorted list, so each
        # item costs a lookup and a bisect.
        find = render.render(
            "{offer}x" * 8000,
            1100.0, "once", {}, "once", [],
        )
        items = [str(200000 + i) for i in range(8000)]
        start = time.process_time()
        reasons = review.review(find, items)
        elapsed = time.process_time() - start
        self.assertIn("text touches a rendered amount", reasons)
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


class ScaleWordRunTest(ReviewFixCase):
    def test_glued_scale_forms_need_approval(self):
        # Scale words match inside letter runs like number words do:
        # "halfmillion" and "thousandfold" are number-shaped, never
        # ordinary words.
        case_id = self.make_case()
        for template in (
            "a halfmillion total",
            "the thousandfold increase",
            "it cost hundredish",
            "a multimillion market",
            "grandtotal due",
            "tengrand flat",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("scale", " ".join(out["reasons"]))

    def test_k_suffix_forms_need_approval(self):
        # A number word plus a scale suffix inside one run still
        # routes: "twok" and "fiftym" read as numbers.
        case_id = self.make_case()
        for template in (
            "about twok",
            "a fiftym cap",
            "tenmil users",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "number word", " ".join(out["reasons"])
                )

    def test_scale_abbreviations_stay_whole_token(self):
        # The one- and two-letter abbreviations are ordinary letters
        # inside a run, so they still match whole tokens only.
        case_id = self.make_case()
        for template in (
            "the milk is cold",
            "a family matter",
            "worth a thou",
            "plan k is third",
        ):
            with self.subTest(template=template):
                if template in ("worth a thou", "plan k is third"):
                    out = self.review(
                        case_id, send_draft(template=template)
                    )
                    self.assertIn("scale", " ".join(out["reasons"]))
                else:
                    self.passed(case_id, send_draft(template=template))

    def test_inflected_common_words_pass(self):
        # Common English words that contain a number word stay on the
        # whole-run exception list, inflections included.
        case_id = self.make_case()
        for template in (
            "the tenure is standard",
            "we listened carefully",
            "we are listening",
            "honestly it is fine",
            "nonetheless we try",
            "she phoned earlier",
            "he is phoning now",
            "a frightened look",
            "an attentive reader",
            "close attention",
            "not intentionally",
            "good intention",
            "a bitten nail",
            "the softened edges",
            "how often does it renew",
            "oftentimes it helps",
            "money is not the issue",
            "a monetary policy",
            "we are done",
            "they are gone",
            "none of it",
            "a stone wall outside",
            "the tone is professional",
            "the toned surface",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))

    def test_wont_is_not_the_currency_won(self):
        # Tokens keep interior apostrophes: "won't" is one token and
        # never the currency word "won".
        case_id = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(template="i won't say")
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["reasons"], [])


class CommitPhraseIsolationTest(BtTestCase):
    def test_each_phrase_flags_on_its_own(self):
        # Deleting any one phrase must fail here: the commit-word
        # list is masked of the phrase's own words, so the phrase is
        # the only thing left that can produce the commitment reason.
        for phrase in sorted(wordlists.COMMIT_PHRASES):
            with self.subTest(phrase=" ".join(phrase)):
                find = render.render(
                    " ".join(phrase), None, "once", {}, "once", []
                )
                remaining = wordlists.COMMIT_WORDS - set(phrase)
                with mock.patch.object(
                    wordlists, "COMMIT_WORDS", remaining
                ):
                    reasons = review.review(find, [])
                self.assertIn(
                    "agreement or commitment wording in the message",
                    reasons,
                )


if __name__ == "__main__":
    unittest.main()
