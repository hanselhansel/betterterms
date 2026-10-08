"""Numeric-bound fixes from the step-2 gate review: hostile offer
magnitudes land as plain blocks, never parser crashes, and
``cases.num`` caps magnitudes at 1e12."""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    BtTestCase,
    new_case,
    plan_for,
    run_bt_json,
    write_case_files,
)
from btlib import cases


class NumCapTest(BtTestCase):
    def make_case(self, direction="pay", floor=1200, plan=None):
        case_id, case_dir = new_case(self.home, direction=direction)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, direction=direction),
            plan=plan_for(direction, floor) if plan is None else plan,
            floor=floor,
        )
        return case_id

    def test_huge_integer_offer_blocks_not_crashes(self):
        # A 400-digit offer used to raise OverflowError inside float();
        # it must come back as a plain block.
        case_id = self.make_case()
        path = self.tmp / "draft.yaml"
        path.write_text(
            "action: send\noffer: " + "9" * 400 + "\ntemplate: hi\n"
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("offer must be a number", out["reasons"])

    def test_overlong_integer_offer_blocks_not_errors(self):
        # Past Python's digit limit the int constructor raises; the
        # offer loads as a string and lands as "not a number" (exit 1),
        # never a YAML parse error (exit 2).
        case_id = self.make_case()
        path = self.tmp / "draft.yaml"
        path.write_text(
            "action: send\noffer: " + "9" * 5000 + "\ntemplate: hi\n"
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("offer must be a number", out["reasons"])

    def test_num_caps_at_1e12(self):
        for bad in (10**400, 1e13, -2e12, float("inf"), float("nan"),
                    "1e13", "9" * 400):
            with self.subTest(bad=repr(bad)[:30]):
                self.assertIsNone(cases.num(bad))
        self.assertEqual(cases.num(1e12), 1e12)
        self.assertEqual(cases.num("999.50"), 999.5)
        self.assertEqual(cases.num("1,200"), 1200.0)


if __name__ == "__main__":
    unittest.main()
