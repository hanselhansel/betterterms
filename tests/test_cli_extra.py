"""The smaller CLI surfaces: ``bt.py where`` prints its own absolute
path, ``case set-terms`` writes target and best_alternative into
plan.yaml, refuses a target on the wrong side of a set walk-away,
and never writes the floor file."""

import os
import stat
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

    def test_set_terms_replaces_plan_atomically(self):
        # plan.yaml lands through the same 0600 temp-plus-rename the
        # held records use: the inode moves on every write, so a
        # reader can never see a torn plan.
        case_id, case_dir = new_case(self.home)
        plan_path = case_dir / "plan.yaml"
        before_ino = plan_path.stat().st_ino
        proc, out = run_bt_json(
            self.home, "case", "set-terms", case_id, "--target", "900"
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertNotEqual(plan_path.stat().st_ino, before_ino)
        self.assertEqual(
            stat.S_IMODE(os.stat(plan_path).st_mode), 0o600
        )
        plan = yaml.load(plan_path.read_text())
        self.assertEqual(plan["target"], 900)

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


class SetTermsFloorTest(BtTestCase):
    """A saved target worse than the walk-away makes every later
    gate call exit 2 on ``plan conflicts with your limits``, so
    set-terms refuses it instead. With no floor the command cannot
    know the side, so it saves as before."""

    WRONG_SIDE = (
        "target is on the wrong side of your walk-away; nothing saved"
    )

    def test_target_above_floor_pay_refused(self):
        case_id, case_dir = new_case(self.home)
        run_bt_json(self.home, "case", "set-floor", case_id, stdin="70\n")
        run_bt_json(
            self.home, "case", "set-terms", case_id, "--target", "60"
        )
        proc, out = run_bt_json(
            self.home,
            "case",
            "set-terms",
            case_id,
            "--target",
            "100",
            "--alternative",
            "55",
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertEqual(out["error"], self.WRONG_SIDE)
        self.assertNotRegex(out["error"], r"\d")
        # The walk-away value never reaches stdout.
        self.assertNotIn("70", proc.stdout)
        # Nothing saved: the old target stands and the alternative
        # never lands.
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 60)
        self.assertIsNone(plan["best_alternative"])

    def test_target_below_floor_receive_refused(self):
        case_id, case_dir = new_case(self.home, direction="receive")
        run_bt_json(self.home, "case", "set-floor", case_id, stdin="70\n")
        run_bt_json(
            self.home, "case", "set-terms", case_id, "--target", "80"
        )
        proc, out = run_bt_json(
            self.home, "case", "set-terms", case_id, "--target", "50"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertEqual(out["error"], self.WRONG_SIDE)
        self.assertNotRegex(out["error"], r"\d")
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 80)

    def test_target_at_floor_saves(self):
        # At the walk-away is inside the band, like the plan check.
        case_id, case_dir = new_case(self.home)
        run_bt_json(self.home, "case", "set-floor", case_id, stdin="70\n")
        proc, out = run_bt_json(
            self.home, "case", "set-terms", case_id, "--target", "70"
        )
        self.assertEqual(proc.returncode, 0, out)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 70)

    def test_no_floor_saves_any_target(self):
        case_id, case_dir = new_case(self.home)
        proc, out = run_bt_json(
            self.home, "case", "set-terms", case_id, "--target", "100"
        )
        self.assertEqual(proc.returncode, 0, out)
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(plan["target"], 100)

    def test_set_terms_still_never_writes_floor(self):
        # The refusal reads the floor but the file is untouched.
        case_id, case_dir = new_case(self.home)
        run_bt_json(self.home, "case", "set-floor", case_id, stdin="70\n")
        floor_stat = (case_dir / ".floor").stat()
        proc, _ = run_bt_json(
            self.home, "case", "set-terms", case_id, "--target", "100"
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(
            (case_dir / ".floor").read_text().strip(), "70.00"
        )
        self.assertEqual(
            (case_dir / ".floor").stat().st_ino, floor_stat.st_ino
        )


if __name__ == "__main__":
    unittest.main()
