"""set-floor hardening: strict number parsing, hidden TTY prompt via
getpass, and a corrupt .floor file blocking the gate and erroring the
scorer."""

import contextlib
import io
import os
import sys
import unittest
from unittest import mock

from bt_helpers import (
    BRIEF_PAY,
    PLAN_BILLS,
    BtTestCase,
    new_case,
    run_bt_json,
    write_case_files,
    write_draft,
)
from btlib import yaml

FLOOR_MSG = "floor must be a single plain number like 1200 or 1200.50"
LIMITS = "outside your limits; escalate to the user"


class SetFloorParseTest(BtTestCase):
    def make_case(self):
        case_id, case_dir = new_case(self.home)
        write_case_files(
            case_dir, brief=dict(BRIEF_PAY), plan=dict(PLAN_BILLS)
        )
        return case_id, case_dir

    def test_accepts_plain_numbers(self):
        case_id, case_dir = self.make_case()
        for raw, want in (
            ("1200", "1200.00"),
            ("1200.50", "1200.50"),
            ("99.9", "99.90"),
            ("  1200 \n", "1200.00"),
        ):
            with self.subTest(raw=raw):
                proc, out = run_bt_json(
                    self.home, "case", "set-floor", case_id, stdin=raw
                )
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(
                    (case_dir / ".floor").read_text().strip(), want
                )

    def test_rejects_non_plain_numbers(self):
        case_id, case_dir = self.make_case()
        rejected = [
            "",
            "   ",
            "abc",
            "nan",
            "NaN",
            "inf",
            "-5",
            "+5",
            "1,200",
            "$1,200.00",
            "85.000",
            "1.234.567",
            "1 200",
            "1000-1200",
            "$1,000 or $1,200",
            "1.2.3",
            ",200",
            "1200,",
            "0x10",
            "1e3",
            "1_000",
            "twelve hundred",
        ]
        for raw in rejected:
            with self.subTest(raw=raw):
                proc, out = run_bt_json(
                    self.home, "case", "set-floor", case_id,
                    stdin=raw + "\n",
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertEqual(out["error"], FLOOR_MSG)
                self.assertFalse((case_dir / ".floor").exists())

    def test_rejected_input_never_echoed_and_floor_kept(self):
        case_id, case_dir = self.make_case()
        run_bt_json(self.home, "case", "set-floor", case_id, stdin="900\n")
        proc, out = run_bt_json(
            self.home, "case", "set-floor", case_id, stdin="$1,200\n"
        )
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("1,200", proc.stdout)
        self.assertNotIn("1,200", proc.stderr)
        self.assertEqual((case_dir / ".floor").read_text().strip(), "900.00")


class SetFloorTtyTest(BtTestCase):
    def test_tty_reads_with_getpass_not_stdin(self):
        import bt as bt_cli

        case_id, case_dir = new_case(self.home)
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = True
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", fake_stdin), mock.patch(
            "getpass.getpass", return_value="1200\n"
        ) as gp, mock.patch.dict(
            os.environ, {"BETTERTERMS_HOME": str(self.home)}
        ), contextlib.redirect_stdout(out):
            code = bt_cli.main(["case", "set-floor", case_id])
        self.assertEqual(code, 0, out.getvalue())
        gp.assert_called_once_with("Walk-away number (hidden): ")
        self.assertFalse(fake_stdin.read.called)
        self.assertEqual((case_dir / ".floor").read_text().strip(), "1200.00")
        self.assertNotIn("1200", out.getvalue())

    def test_non_tty_reads_stdin(self):
        import bt as bt_cli

        case_id, case_dir = new_case(self.home)
        fake_stdin = io.StringIO("1100\n")
        fake_stdin.isatty = lambda: False
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", fake_stdin), mock.patch(
            "getpass.getpass"
        ) as gp, mock.patch.dict(
            os.environ, {"BETTERTERMS_HOME": str(self.home)}
        ), contextlib.redirect_stdout(out):
            code = bt_cli.main(["case", "set-floor", case_id])
        self.assertEqual(code, 0, out.getvalue())
        self.assertFalse(gp.called)
        self.assertEqual((case_dir / ".floor").read_text().strip(), "1100.00")


class CorruptFloorTest(BtTestCase):
    def make_case(self):
        case_id, case_dir = new_case(self.home)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY),
            plan=dict(PLAN_BILLS),
            floor=1200,
        )
        return case_id, case_dir

    def gate(self, case_id):
        path = write_draft(
            self.tmp,
            {"action": "send", "offer": 1100, "template": "hi",
             "claims": []},
        )
        return run_bt_json(self.home, "gate", case_id, "--draft", str(path))

    def score(self, case_id):
        path = self.tmp / "inbound.yaml"
        path.write_text(yaml.dump({"offer": 80, "text": "counter"}))
        return run_bt_json(self.home, "score", case_id, "--inbound", str(path))

    def test_non_finite_or_bad_floor_blocks_gate_errors_score(self):
        case_id, case_dir = self.make_case()
        for content in ("nan\n", "inf\n", "-5\n", "not a number\n", ""):
            with self.subTest(content=content):
                (case_dir / ".floor").write_text(content)
                proc, out = self.gate(case_id)
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["result"], "block")
                self.assertIn(LIMITS, out["reasons"])
                proc, out = self.score(case_id)
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)

    @unittest.skipIf(
        os.name == "nt" or os.geteuid() == 0, "needs a non-root POSIX user"
    )
    def test_unreadable_floor_blocks_gate_errors_score(self):
        case_id, case_dir = self.make_case()
        path = case_dir / ".floor"
        path.chmod(0)
        self.addCleanup(path.chmod, 0o600)
        proc, out = self.gate(case_id)
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn(LIMITS, out["reasons"])
        proc, out = self.score(case_id)
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
