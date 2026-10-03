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
        self.assertEqual(floor_path.read_text().strip(), "1200.00")

    def test_set_floor_rejects_currency_text(self):
        # Strict parsing: only a plain number like 1200 or 1200.50. A
        # currency string or a separator the user could mean two ways is
        # refused instead of guessed.
        case_id, case_dir = new_case(self.home)
        proc, out = run_bt_json(self.home, "case", "set-floor", case_id, stdin="$1,200.00\n")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertNotIn("1,200", proc.stdout)
        self.assertFalse((case_dir / ".floor").exists())
        proc, out = run_bt_json(self.home, "case", "set-floor", case_id, stdin="1200.00\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("1200", proc.stdout)
        self.assertEqual((case_dir / ".floor").read_text().strip(), "1200.00")

    def test_case_show_omits_floor(self):
        case_id, case_dir = new_case(self.home)
        run_bt_json(self.home, "case", "set-floor", case_id, stdin="1200\n")
        proc, out = run_bt_json(self.home, "case", "show", case_id)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("brief", out)
        self.assertIn("plan", out)
        self.assertNotIn("floor", out)
        self.assertNotIn("1200", proc.stdout)

    def test_case_show_with_date_deadline_outputs_json(self):
        # YAML 1.1 loads an ISO date as datetime.date; case show must
        # still emit JSON instead of crashing in json.dumps.
        case_id, case_dir = new_case(self.home)
        (case_dir / "brief.yaml").write_text(
            "pack: bills\nmode: act\ndirection: pay\ndeadline: 2026-11-01\n"
        )
        proc, out = run_bt_json(self.home, "case", "show", case_id)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(out["brief"]["deadline"], "2026-11-01")

    def test_case_show_approvals_load_as_booleans(self):
        # approved_by_user: yes|no and friends are booleans under YAML 1.1.
        case_id, case_dir = new_case(self.home)
        (case_dir / "brief.yaml").write_text(
            "pack: bills\nmode: act\ndirection: pay\napproved_by_user: yes\n"
        )
        proc, out = run_bt_json(self.home, "case", "show", case_id)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIs(out["brief"]["approved_by_user"], True)

    def test_case_show_unknown_errors(self):
        proc, out = run_bt_json(self.home, "case", "show", "bills-20000101-0000")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_set_floor_unknown_case_errors(self):
        proc, _ = run_bt_json(self.home, "case", "set-floor", "bills-20000101-0000", stdin="5")
        self.assertEqual(proc.returncode, 2)

    # Extended by /ship coverage audit: the range and two-number rows.
    # Value: protects=set-floor refuses a range or two amounts and writes no
    # .floor; fails_when=parse_number takes the first or last amount found;
    # why_new=only a no-number input ("abc") was tested; seam=none
    def test_set_floor_bad_value_errors(self):
        case_id, case_dir = new_case(self.home)
        for raw in ("abc\n", "1000-1200\n", "$1,000 or $1,200\n"):
            with self.subTest(raw=raw):
                proc, out = run_bt_json(
                    self.home, "case", "set-floor", case_id, stdin=raw
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)
                self.assertFalse((case_dir / ".floor").exists())

    # Generated by /ship coverage audit.
    # Value: protects=a rejected set-floor input never appears in the
    # error output, so the typed floor cannot leak into transcripts;
    # fails_when=parse_number echoes the raw input again; why_new=exit
    # status was tested, message contents were not; seam=none
    def test_set_floor_error_never_echoes_input(self):
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(
            self.home, "case", "set-floor", case_id, stdin="$1,000 or $1,200\n"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertEqual(
            out["error"],
            "floor must be a single plain number like 1200 or 1200.50",
        )
        self.assertNotIn("1,000", proc.stdout)
        self.assertNotIn("1,200", proc.stdout)
        self.assertNotIn("1,000", proc.stderr)

    # Generated by /ship coverage audit.
    # Value: protects=case new refuses a pack name outside [a-z0-9-] and
    # exits 2 before anything is created; fails_when=PACK_RE is loosened
    # or the check moves after mkdir; why_new=only well-formed packs were
    # exercised; seam=none
    def test_case_new_bad_pack_errors(self):
        for pack in ("Bad Pack", "pack!", "../x", ""):
            with self.subTest(pack=pack):
                proc, out = run_bt_json(
                    self.home, "case", "new", "--pack", pack
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)
        self.assertFalse((self.home / "cases").exists())

    # Generated by /ship coverage audit.
    # Value: protects=case show returns null brief and plan fields when
    # those files are absent instead of erroring; fails_when=the is_file
    # guards in cmd_case_show are dropped; why_new=show was only run on
    # fully written cases; seam=none
    def test_case_show_missing_brief_and_plan_gives_nulls(self):
        case_id, case_dir = new_case(self.home)
        (case_dir / "brief.yaml").unlink()
        (case_dir / "plan.yaml").unlink()
        proc, out = run_bt_json(self.home, "case", "show", case_id)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIsNone(out["brief"])
        self.assertIsNone(out["plan"])


if __name__ == "__main__":
    unittest.main()
