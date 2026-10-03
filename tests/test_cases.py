import os
import re
import stat
import unittest
from pathlib import Path

from bt_helpers import BtTestCase, new_case, run_bt, run_bt_json

CASE_ID_RE = re.compile(r"^[a-z0-9-]+-\d{8}-[0-9a-f]{4}$")


class CaseTest(BtTestCase):
    def test_case_id_format(self):
        case_id, case_dir = new_case(self.home, pack="bills")
        self.assertRegex(case_id, CASE_ID_RE)
        self.assertTrue(case_id.startswith("bills-"))
        self.assertTrue(case_dir.is_dir())
        self.assertEqual(case_dir, self.home / "cases" / case_id)

    def test_case_new_layout(self):
        _, case_dir = new_case(self.home)
        self.assertTrue((case_dir / "brief.yaml").is_file())
        self.assertTrue((case_dir / "plan.yaml").is_file())
        self.assertTrue((case_dir / "sources").is_dir())
        self.assertTrue((case_dir / "thread.md").is_file())

    def test_home_env_override(self):
        proc = run_bt(self.home, "case", "new", "--pack", "bills")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.home / "cases").is_dir())

    def test_set_floor_hidden_and_mode(self):
        case_id, case_dir = new_case(self.home)
        proc, out = run_bt_json(self.home, "case", "set-floor", case_id, stdin="1200\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out, {"ok": True})
        self.assertNotIn("1200", proc.stdout)
        floor_path = case_dir / ".floor"
        self.assertTrue(floor_path.is_file())
        mode = stat.S_IMODE(os.stat(floor_path).st_mode)
        self.assertEqual(mode, 0o600, oct(mode))
        self.assertEqual(floor_path.read_text().strip(), "1200")

    def test_set_floor_parses_currency_text(self):
        case_id, case_dir = new_case(self.home)
        proc, out = run_bt_json(self.home, "case", "set-floor", case_id, stdin="$1,200.00\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("1200", proc.stdout)
        self.assertEqual((case_dir / ".floor").read_text().strip(), "1200")

    def test_case_show_omits_floor(self):
        case_id, case_dir = new_case(self.home)
        run_bt_json(self.home, "case", "set-floor", case_id, stdin="1200\n")
        proc, out = run_bt_json(self.home, "case", "show", case_id)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("brief", out)
        self.assertIn("plan", out)
        self.assertNotIn("floor", out)
        self.assertNotIn("1200", proc.stdout)

    def test_case_show_unknown_errors(self):
        proc, out = run_bt_json(self.home, "case", "show", "bills-20000101-0000")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_set_floor_unknown_case_errors(self):
        proc, _ = run_bt_json(self.home, "case", "set-floor", "bills-20000101-0000", stdin="5")
        self.assertEqual(proc.returncode, 2)

    def test_set_floor_bad_value_errors(self):
        case_id, _ = new_case(self.home)
        proc, _ = run_bt_json(self.home, "case", "set-floor", case_id, stdin="abc\n")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
