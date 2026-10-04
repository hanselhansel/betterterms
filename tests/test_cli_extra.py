"""The smaller CLI surfaces: ``bt.py where`` prints its own absolute
path, ``case set-terms`` writes target and best_alternative into
plan.yaml without ever touching the floor file."""

import os
import unittest

from bt_helpers import (
    BT,
    BtTestCase,
    new_case,
    run_bt_json,
)
from btlib import yaml


class WhereTest(BtTestCase):
    def test_where_prints_absolute_path(self):
        proc, out = run_bt_json(self.home, "where")
        self.assertEqual(proc.returncode, 0, out)
        self.assertTrue(os.path.isabs(out["bt"]), out)
        self.assertTrue(os.path.samefile(out["bt"], BT))


class SetTermsTest(BtTestCase):
    def test_set_terms_writes_plan(self):
        case_id, case_dir = new_case(self.home)
        proc, out = run_bt_json(
            self.home,
            "case",
            "set-terms",
            case_id,
            "--target",
            "900",
            "--alternative",
            "60",
            "--period",
            "month",
            "--note",
            "Verizon quote, 2026-10-01",
        )
        self.assertEqual(proc.returncode, 0, out)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 900)
        self.assertEqual(
            plan["best_alternative"],
            {
                "amount": 60,
                "period": "month",
                "note": "Verizon quote, 2026-10-01",
            },
        )

    def test_set_terms_never_touches_floor(self):
        case_id, case_dir = new_case(self.home)
        run_bt_json(
            self.home, "case", "set-floor", case_id, stdin="1200\n"
        )
        proc, out = run_bt_json(
            self.home,
            "case",
            "set-terms",
            case_id,
            "--target",
            "1,100",
            "--alternative",
            "$60.50",
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            (case_dir / ".floor").read_text().strip(), "1200.00"
        )
        self.assertNotIn("1200", proc.stdout)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 1100)
        self.assertEqual(plan["best_alternative"]["amount"], 60.5)

    def test_set_terms_bad_period_errors(self):
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(
            self.home,
            "case",
            "set-terms",
            case_id,
            "--alternative",
            "60",
            "--period",
            "weekly",
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("period", out["error"])

    def test_set_terms_bad_amount_errors(self):
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(
            self.home,
            "case",
            "set-terms",
            case_id,
            "--target",
            "sixty",
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)

    def test_set_terms_nothing_to_set_errors(self):
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(
            self.home, "case", "set-terms", case_id
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
