"""Gate word-list fixes deferred from the step-2 ship (TODOS.md):
possessive and contraction suffixes strip before whole-token
matching, the missing scale, currency, commitment and number words
join the lists, and a plan at the input cap still gates in under a
second. Every flag routes to the user; nothing new passes silently.
"""

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


class WordlistCase(BtTestCase):
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


class SuffixStripTest(WordlistCase):
    def test_possessive_suffix_still_flags(self):
        # "deal's", "dollar's", "USD's" and "k's" hid behind the 's:
        # the possessive strips before the whole-token lists match.
        case_id = self.make_case()
        for template, fragment in (
            ("the deal's done", "commitment"),
            ("the agreement's terms", "commitment"),
            ("a dollar's worth", "currency"),
            ("the buck's stopped", "currency"),
            ("the USD's rate", "currency"),
            ("about k's worth", "scale"),
            ("the dong's rate", "currency"),
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(fragment, " ".join(out["reasons"]))

    def test_stripping_never_invents_a_word(self):
        # The strip only removes a suffix; "let's" loses 's to "let",
        # "won't" loses n't to "wo", never "won".
        case_id = self.make_case()
        for template in (
            "let's talk soon",
            "i won't say",
            "that's the rate",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))


class NewWordTest(WordlistCase):
    def test_new_scale_words_flag(self):
        case_id = self.make_case()
        for template in (
            "a lakh total",
            "the crore figure",
            "a quadrillion scale",
            "an mn market",
            "the mln count",
            "a bln gap",
            "the tn figure",
            "a bil market",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("scale", " ".join(out["reasons"]))

    def test_new_currency_words_flag(self):
        case_id = self.make_case()
        for template in (
            "the franc amount",
            "a pence piece",
            "one penny",
            "the rupiah price",
            "a ruble value",
            "the dinar rate",
            "paid in sterling",
            "two dirhams",
            "a few kronor",
            "some shekels",
            "several lire",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("currency", " ".join(out["reasons"]))

    def test_new_currency_codes_flag_case_sensitively(self):
        case_id = self.make_case()
        for template in ("an RMB price", "the BTC wallet"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("currency", " ".join(out["reasons"]))
        for template in ("the rmb wallet", "a btc wallet"):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))

    def test_new_commitment_forms_flag(self):
        case_id = self.make_case()
        for template in (
            "she agrees today",
            "we got charged",
            "they are cancelling",
            "the cancellation fee",
            "already paid",
            "still paying",
            "two deals done",
            "sign us up today",
            "count us in please",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("commitment", " ".join(out["reasons"]))

    def test_dozen_and_late_ordinals_flag(self):
        # Ordinals that share a number-word stem flagged already;
        # fifth, ninth and twelfth complete the set with dozen.
        case_id = self.make_case()
        for template in (
            "a dozen units",
            "the fifth offer",
            "on the ninth",
            "the twelfth call",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("number word", " ".join(out["reasons"]))

    def test_common_ordinal_words_stay_clean(self):
        # first, second and third are ordinary English like "often":
        # they stay off the list so everyday text still passes.
        case_id = self.make_case()
        for template in (
            "the first draft",
            "a second opinion",
            "the third call",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))


class LargePlanTest(WordlistCase):
    def test_plan_at_the_input_cap_gates_under_one_second(self):
        # Input files cap at 64 KB before parsing; the largest plan
        # that fits, about 2,600 terse facts, parses in tenths of a
        # second and the whole gate run stays under one.
        plan = dict(
            plan_for("pay", 1200),
            facts=[
                {"id": f"f{i}", "text": "a"}
                for i in range(2600)
            ],
        )
        case_id = self.make_case(plan=plan)
        start = time.monotonic()
        proc, out = self.gate(
            case_id, send_draft(template="hi")
        )
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertEqual(proc.returncode, 0, out)


if __name__ == "__main__":
    unittest.main()
