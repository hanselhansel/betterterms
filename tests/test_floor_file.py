""".floor file hardening (adversarial review fixes): set-floor writes a
canonical two-decimal value to a fresh 0600 temp file that is fsynced
and renamed into place, and refuses a symlinked or non-regular target;
read_floor lstat-checks the file and treats anything but a regular
file as missing; case directories are created 0700; name checks match
the whole string so a trailing newline cannot smuggle a name past.
"""

import os
import stat
import unittest

from bt_helpers import (
    BRIEF_PAY,
    PLAN_BILLS,
    BtTestCase,
    new_case,
    run_bt,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)

FLOOR_MSG = "floor must be a single plain number like 1200 or 1200.50"
FLOOR_MIN = "floor must be at least 0.01"
LIMITS = "outside your limits; escalate to the user"


class FloorFileCase(BtTestCase):
    def make_case(self, floor=None):
        case_id, case_dir = new_case(self.home)
        # No saved target: set-floor now refuses a walk-away on the
        # wrong side of one, and these floors are file-mechanics
        # fixtures, not conflict checks.
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY),
            plan=dict(PLAN_BILLS, target=None),
            floor=floor,
        )
        return case_id, case_dir

    def set_floor(self, case_id, raw):
        return run_bt_json(
            self.home, "case", "set-floor", case_id, stdin=raw
        )

    def gate(self, case_id):
        path = write_draft(self.tmp, send_draft(template="hi"))
        return run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )


class SetFloorAtomicTest(FloorFileCase):
    def test_symlinked_floor_is_refused_and_untouched(self):
        # A planted .floor symlink must never be followed: set-floor
        # refuses, the link and its target stay exactly as they were.
        case_id, case_dir = self.make_case()
        target = self.tmp / "elsewhere.txt"
        target.write_text("999\n")
        link = case_dir / ".floor"
        os.symlink(target, link)
        proc, out = self.set_floor(case_id, "100\n")
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(), "999\n")

    def test_non_regular_floor_target_refused(self):
        # A .floor that is a directory is refused the same way.
        case_id, case_dir = self.make_case()
        (case_dir / ".floor").mkdir()
        proc, out = self.set_floor(case_id, "100\n")
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)
        self.assertTrue((case_dir / ".floor").is_dir())

    def test_written_floor_is_regular_0600(self):
        case_id, case_dir = self.make_case()
        proc, out = self.set_floor(case_id, "1200.50\n")
        self.assertEqual(proc.returncode, 0, out)
        path = case_dir / ".floor"
        st = os.lstat(path)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertFalse(stat.S_ISLNK(st.st_mode))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        # The canonical store form keeps exactly two decimals.
        self.assertEqual(path.read_text(), "1200.50\n")

    def test_canonical_two_decimal_storage(self):
        case_id, case_dir = self.make_case()
        for raw, want in (
            ("1200", "1200.00"),
            ("1200.50", "1200.50"),
            ("99.9", "99.90"),
            ("0.01", "0.01"),
            ("  1200 \n", "1200.00"),
        ):
            with self.subTest(raw=raw):
                proc, out = self.set_floor(case_id, raw)
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(
                    (case_dir / ".floor").read_text(), want + "\n"
                )

    def test_rejects_more_than_two_decimals(self):
        # A value with a third decimal cannot be stored exactly at 2
        # decimals; it is rejected before any byte is written.
        case_id, case_dir = self.make_case()
        for raw in ("100.004", "1.2345", "85.000", "0.009", "0.001"):
            with self.subTest(raw=raw):
                proc, out = self.set_floor(case_id, raw + "\n")
                self.assertEqual(proc.returncode, 2, out)
                self.assertEqual(out["error"], FLOOR_MSG)
                self.assertFalse((case_dir / ".floor").exists())

    def test_rejects_tiny_values_below_one_cent(self):
        case_id, case_dir = self.make_case()
        for raw in ("0", "0.0", "0.00"):
            with self.subTest(raw=raw):
                proc, out = self.set_floor(case_id, raw + "\n")
                self.assertEqual(proc.returncode, 2, out)
                self.assertEqual(out["error"], FLOOR_MIN)
                self.assertFalse((case_dir / ".floor").exists())

    def test_rejected_input_leaves_existing_floor(self):
        # The value parses before anything is written, so a bad input
        # never truncates the floor already on file.
        case_id, case_dir = self.make_case()
        proc, _ = self.set_floor(case_id, "900\n")
        self.assertEqual(proc.returncode, 0)
        proc, out = self.set_floor(case_id, "100.004\n")
        self.assertEqual(proc.returncode, 2, out)
        self.assertEqual((case_dir / ".floor").read_text(), "900.00\n")

    def test_round_trip_read_floor(self):
        # What set-floor stores is exactly what the gate reads: a
        # 1234.56 floor routes a matching send offer as at-limit.
        case_id, _ = self.make_case()
        proc, _ = self.set_floor(case_id, "1234.56\n")
        self.assertEqual(proc.returncode, 0)
        path = write_draft(
            self.tmp,
            send_draft(offer=1234.56, template="final is {offer}"),
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("offer is at your limit", out["reasons"])


class ReadFloorHardeningTest(FloorFileCase):
    def test_symlinked_floor_blocks_gate(self):
        case_id, case_dir = self.make_case()
        target = self.tmp / "floor.txt"
        target.write_text("1200\n")
        os.symlink(target, case_dir / ".floor")
        proc, out = self.gate(case_id)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_non_regular_floor_blocks_gate(self):
        case_id, case_dir = self.make_case()
        (case_dir / ".floor").mkdir()
        proc, out = self.gate(case_id)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_invalid_utf8_floor_blocks_never_crashes(self):
        # Undecodable bytes in .floor are a missing floor: a generic
        # block reason, never an exit-2 decode failure.
        case_id, case_dir = self.make_case()
        (case_dir / ".floor").write_bytes(b"\xff\xfe\x001200")
        proc, out = self.gate(case_id)
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn(LIMITS, out["reasons"])


class CaseDirModeTest(BtTestCase):
    def test_case_dirs_created_0700(self):
        case_id, case_dir = new_case(self.home)
        for d in (self.home, self.home / "cases", case_dir,
                  case_dir / "sources"):
            with self.subTest(d=d.name):
                self.assertEqual(
                    stat.S_IMODE(os.stat(d).st_mode), 0o700
                )


class NameCheckTest(BtTestCase):
    def test_pack_name_must_fully_match(self):
        # A trailing newline used to slip past ``re.match`` with an
        # anchored pattern; ``fullmatch`` closes it.
        proc, out = run_bt_json(
            self.home, "case", "new", "--pack", "bills\n"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("bad pack name", out["error"])

    def test_case_id_must_fully_match(self):
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(
            self.home, "case", "show", case_id + "\n"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("bad case id", out["error"])


if __name__ == "__main__":
    unittest.main()
