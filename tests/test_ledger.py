import unittest

from bt_helpers import BtTestCase, new_case, run_bt_json


class LedgerTest(BtTestCase):
    def test_ledger_add_monthly(self):
        case_id, _ = new_case(self.home, pack="bills")
        proc, out = run_bt_json(
            self.home,
            "ledger", "add", case_id,
            "--before", "80", "--after", "60", "--period", "month",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["saved_per_year"], 240)

    def test_ledger_add_yearly(self):
        case_id, _ = new_case(self.home, pack="bills")
        proc, out = run_bt_json(
            self.home,
            "ledger", "add", case_id,
            "--before", "1200", "--after", "960", "--period", "year",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["saved_per_year"], 240)

    def test_ledger_add_receive_direction(self):
        case_id, _ = new_case(self.home, pack="job-offer", direction="receive")
        proc, out = run_bt_json(
            self.home,
            "ledger", "add", case_id,
            "--before", "150000", "--after", "165000", "--period", "year",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["saved_per_year"], 15000)

    def test_ledger_total_sums_by_pack(self):
        c1, _ = new_case(self.home, pack="bills")
        c2, _ = new_case(self.home, pack="subscriptions")
        run_bt_json(self.home, "ledger", "add", c1,
                    "--before", "80", "--after", "60", "--period", "month")
        run_bt_json(self.home, "ledger", "add", c2,
                    "--before", "50", "--after", "40", "--period", "month")
        proc, out = run_bt_json(self.home, "ledger", "total")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["cases"], 2)
        self.assertEqual(out["saved_per_year"], 360)
        self.assertEqual(out["by_pack"], {"bills": 240, "subscriptions": 120})

    def test_ledger_total_empty(self):
        proc, out = run_bt_json(self.home, "ledger", "total")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["cases"], 0)
        self.assertEqual(out["saved_per_year"], 0)
        self.assertEqual(out["by_pack"], {})

    def test_ledger_add_unknown_case_errors(self):
        proc, _ = run_bt_json(
            self.home, "ledger", "add", "bills-20000101-0000",
            "--before", "80", "--after", "60", "--period", "month",
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
