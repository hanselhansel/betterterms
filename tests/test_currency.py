"""Declared currency (adversarial review fix): brief and plan carry a
three-letter ISO ``currency`` (default USD); the renderer prefixes the
matching symbol (USD $, SGD S$, EUR euro sign, GBP pound sign) or the
plain code for anything else; the ledger records each entry's currency
and totals group by it, never adding different currencies together.
"""

import json
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


class CurrencyCase(BtTestCase):
    def make_case(self, plan=None, brief=None, floor=1200):
        case_id, case_dir = new_case(self.home)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, **(brief or {})),
            plan=plan if plan is not None else plan_for("pay", floor),
            floor=floor,
        )
        return case_id

    def gate(self, case_id, draft):
        path = write_draft(self.tmp, draft)
        return run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )


class RenderCurrencyTest(CurrencyCase):
    def offer_text(self, currency):
        plan = dict(plan_for("pay", 1200), currency=currency)
        case_id = self.make_case(plan=plan)
        return self.gate(case_id, send_draft(template="the {offer} tier"))

    def test_declared_symbols_render(self):
        for code, mark in (
            ("USD", "$1,100"),
            ("EUR", "€1,100"),
            ("GBP", "£1,100"),
            ("SGD", "S$1,100"),
            ("CHF", "CHF 1,100"),
        ):
            with self.subTest(code=code):
                proc, out = self.offer_text(code)
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(out["rendered"], f"the {mark} tier")

    def test_lowercase_code_normalizes(self):
        proc, out = self.offer_text("eur")
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "the €1,100 tier")

    def test_absent_currency_defaults_usd(self):
        plan = dict(plan_for("pay", 1200))
        plan.pop("currency", None)
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(case_id, send_draft(template="the {offer} tier"))
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "the $1,100 tier")

    def test_brief_currency_applies_when_plan_silent(self):
        plan = dict(plan_for("pay", 1200))
        plan.pop("currency", None)
        case_id = self.make_case(plan=plan, brief={"currency": "GBP"})
        proc, out = self.gate(case_id, send_draft(template="the {offer} tier"))
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "the £1,100 tier")

    def test_option_target_quote_render_in_currency(self):
        plan = dict(
            plan_for("pay", 1200),
            currency="EUR",
            options=[{"label": "a", "value": 1100, "kind": "price"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(template="{option:a} or {target}"),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "€1,100 or €1,000")


class CurrencyValidationTest(CurrencyCase):
    def test_invalid_currency_exits_2(self):
        for bad in ("US", "USDD", "U$D", 123, ["USD"], "€"):
            with self.subTest(bad=bad):
                plan = dict(plan_for("pay", 1200), currency=bad)
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(
                    case_id, send_draft(template="the {offer} tier")
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("currency", out["error"])

    def test_conflicting_brief_plan_currency_exits_2(self):
        # A plan in EUR against a brief in USD is a broken case file:
        # which currency the floor means is unknowable.
        plan = dict(plan_for("pay", 1200), currency="EUR")
        case_id = self.make_case(plan=plan, brief={"currency": "USD"})
        proc, out = self.gate(case_id, send_draft(template="the {offer} tier"))
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("different currencies", out["error"])


class LedgerCurrencyTest(CurrencyCase):
    def add(self, case_id, before=80, after=60, period="month"):
        return run_bt_json(
            self.home,
            "ledger", "add", case_id,
            "--before", str(before), "--after", str(after),
            "--period", period,
        )

    def test_entry_records_plan_currency(self):
        plan = dict(plan_for("pay", 1200), currency="EUR")
        case_id = self.make_case(plan=plan)
        proc, out = self.add(case_id)
        self.assertEqual(proc.returncode, 0, out)
        lines = (self.home / "ledger.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(lines[0])["currency"], "EUR")

    def test_total_groups_by_currency_never_adds(self):
        # 240 USD/year and 240 EUR/year are two totals, never 480.
        usd = self.make_case(plan=dict(plan_for("pay", 1200)))
        eur = self.make_case(
            plan=dict(plan_for("pay", 1200), currency="EUR")
        )
        self.add(usd)
        self.add(eur)
        proc, out = run_bt_json(self.home, "ledger", "total")
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            out["by_currency"], {"EUR": 240, "USD": 240}
        )
        self.assertEqual(
            out["by_pack"],
            {"bills": {"EUR": 240, "USD": 240}},
        )
        self.assertNotIn("saved_per_year", out)

    def test_entry_without_currency_groups_unknown(self):
        case_id = self.make_case()
        self.add(case_id)
        lines = (self.home / "ledger.jsonl").read_text().splitlines()
        record = json.loads(lines[0])
        del record["currency"]
        (self.home / "ledger.jsonl").write_text(
            json.dumps(record) + "\n"
        )
        proc, out = run_bt_json(self.home, "ledger", "total")
        self.assertEqual(out["by_currency"], {"unknown": 240})


if __name__ == "__main__":
    unittest.main()
