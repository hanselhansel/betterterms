"""Review-tier allowlist contract (decision 0009 amendment): on the
rendered message with each non-fact placeholder output masked by a
sentinel, free text passes only when every character is on the allowed
set, every token is clean and no whole-word list matches. Fact text is
scanned by the same rules."""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    REPO,
    BtTestCase,
    inbound_msg,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import wordlists, yaml

LIMITS = "outside your limits; escalate to the user"


class AllowlistCase(BtTestCase):
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


class CharacterSetTest(AllowlistCase):
    def test_full_allowed_set_passes(self):
        case_id = self.make_case()
        self.passed(
            case_id,
            send_draft(
                template="ok, so: (this) is fine; a/b & c - d! "
                'really? \'yes\' "sure"... right\nsecond line'
            ),
        )

    def test_every_other_character_needs_approval(self):
        case_id = self.make_case()
        probes = [
            "caf\u00e9 au lait",    # non-ASCII letter
            "a ~50 discount",       # tilde
            "it is 50% off",        # percent sign
            "note_this_here",       # underscore
            "star * here",          # asterisk
            "a + b",                # plus
            "x = y",                # equals
            "ring @ noon",          # at sign
            "tag #1",               # hash
            "tab\tinside",
            "cr\rahead",
            "12\u00a000",           # no-break space (Zs)
            "12\u202f00",           # narrow no-break space (Zs)
            "see\u3164you",         # hangul filler
            "blank\u2800here",      # braille blank
            "pri\ue000vate",        # private use (Co)
            "it costs \u00a3100",   # pound sign
            "it costs \u20ac100",   # euro sign
            "price is $100",        # dollar sign
            "bell\x07here",         # control char
            "soft\u00adhyphen",     # soft hyphen (Cf)
            "zero\u200bwidth",      # zero-width space (Cf)
            "combining a\u0301",    # combining acute (Mn)
            "superscript \u00b2",   # superscript two
            "digit \u0661",         # arabic-indic digit
            "fullwidth \uff11",     # fullwidth digit
        ]
        for template in probes:
            with self.subTest(template=template.encode("unicode_escape")):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "unusual characters", " ".join(out["reasons"])
                )

    def test_non_english_always_needs_approval(self):
        # A documented consequence: natural non-English text carries
        # non-ASCII letters or symbols, so it always routes to the user.
        case_id = self.make_case()
        for template in ("pagar\u00e9", "плачу", "\u652f\u6255\u3046",
                         "\u00bfcu\u00e1nto?"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "unusual characters", " ".join(out["reasons"])
                )


class TokenRuleTest(AllowlistCase):
    def test_mixed_letter_digit_tokens_need_approval(self):
        case_id = self.make_case()
        for template in (
            "call it 95USD",
            "order 12hundred now",
            "that is 2ndly",
            "see note f9",
            "the 20x zoom",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(
                    "letters and digits", " ".join(out["reasons"])
                )

    def test_digit_only_token_rules(self):
        case_id = self.make_case()
        for template in (
            "only 3 left in stock",
            "renewal in 12 months",
            "5 years is the term",
            "we met in 96",
            "section 90 covers this",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))
        for template in (
            "order 1200 today",
            "about 100 units",
            "call 555 now",
            "the count is 0",
            "in 2026 alone",
            "code 1'200",
            "the cap is 1 200",
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_decimal_tokens_need_approval(self):
        # Decision 0010: decimals are number-shaped and route to the
        # user; "90.5" and "3.11" no longer read as small integers.
        case_id = self.make_case()
        for template in ("rate 90.5 today", "build 3.11 here"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_year_after_whole_word_month(self):
        case_id = self.make_case()
        for template in (
            "see you October 15, 2026",
            "due 15 October 2026",
            "in Jan 2026",
            "meeting Jan 15, 2026",
            "renewal December 31, 2099",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))
        for template in (
            "due Janu 15, 2026",      # prefix, not a whole month word
            "meet Sept 15, 2026",     # sept is not on the month list
            "see October 15 2026",    # day form needs the comma
            "plan October 32, 2026",  # day out of range
            "in 2026 October",        # the year must follow the month
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("a number", " ".join(out["reasons"]))

    def test_word_lists_match_whole_tokens(self):
        case_id = self.make_case()
        for template, fragment in (
            ("call it 12 usd flat", "currency"),
            ("a TRY option", "currency"),
            ("the CAD files", "currency"),
            ("a few bucks more", "currency"),
            ("it is in euros", "currency"),
            ("fifty pounds", "currency"),
            ("a grand total", "currency"),
            ("ten yen", "currency"),
            ("1.5 thousand", "scale"),
            ("a bn market", "scale"),
            ("about 1.2 k", "scale"),
            ("twelve hundred", "scale"),
            ("two million", "scale"),
            ("sounds good to me", "commitment"),
            ("that works for us", "commitment"),
            ("I agreed to it", "commitment"),
            ("plan k is third", "scale"),
            ("worth a thou", "scale"),
            ("I have two options for you", "number word"),
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(fragment, " ".join(out["reasons"]))
        # word-shaped codes match in uppercase only.
        for template in (
            "we can try it",
            "a cad design",
        ):
            with self.subTest(template=template):
                self.passed(case_id, send_draft(template=template))

    def test_number_word_runs_need_approval(self):
        case_id = self.make_case()
        for template in ("one two zero zero", "twenty one days"):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn("number word", " ".join(out["reasons"]))


class SentinelAndFactTest(AllowlistCase):
    def test_sentinel_touching_letter_or_digit(self):
        case_id = self.make_case()
        for template, fragment in (
            ("I can do {offer}0 today", "a digit next to"),
            ("I can do {offer}k today", "touches a rendered amount"),
            ("I can do {offer}.99 today", "touches a rendered amount"),
        ):
            with self.subTest(template=template):
                out = self.review(case_id, send_draft(template=template))
                self.assertIn(fragment, " ".join(out["reasons"]))

    def test_fact_text_scanned_by_the_same_allowlist(self):
        plan = dict(
            plan_for("pay", 1200),
            facts=[
                {"id": "fx", "text": "quoted \u20ac100 flat",
                 "source": "x"},
                {"id": "fy", "text": "their code f9", "source": "x"},
            ],
        )
        case_id = self.make_case(plan=plan)
        out = self.review(case_id, send_draft(template="see {fact:fx}"))
        self.assertIn("unusual characters", " ".join(out["reasons"]))
        out = self.review(case_id, send_draft(template="see {fact:fy}"))
        self.assertIn("letters and digits", " ".join(out["reasons"]))

class WordlistDocTest(BtTestCase):
    def test_guardrails_skill_quotes_the_module_lists(self):
        skill = (REPO / "skills" / "betterterms-guardrails" /
                 "SKILL.md").read_text()
        groups = (
            ("number words", wordlists.NUMBER_WORDS),
            ("scale words", wordlists.SCALE_WORDS),
            ("currency codes", wordlists.CURRENCY_CODES),
            ("currency words", wordlists.CURRENCY_WORDS),
            ("commitment words", wordlists.COMMIT_WORDS),
            ("commitment phrases",
             {" ".join(p) for p in wordlists.COMMIT_PHRASES}),
            ("month words", wordlists.MONTH_WORDS),
        )
        for label, words in groups:
            with self.subTest(label=label):
                expected = label + ": " + ", ".join(sorted(words))
                self.assertIn(expected, skill)


if __name__ == "__main__":
    unittest.main()
