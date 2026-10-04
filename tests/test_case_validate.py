"""Case-file validation hardening: plan-vs-floor consistency, option
kinds and periods, brief normalization, case-id safety and the CLI's
JSON-only error contract."""

import contextlib
import io
import json
import unittest

from bt_helpers import (
    approve_held,
    BRIEF_PAY,
    BtTestCase,
    new_case,
    plan_for,
    run_bt,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import yaml


class CaseValidateTest(BtTestCase):
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
        return case_id, case_dir

    def gate(self, case_id, draft, inbound=None, approved=False):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        if approved:
            args = approve_held(self.home, case_id, args)
        return run_bt_json(self.home, *args)

    def test_plan_inconsistent_errors(self):
        case_id, case_dir = self.make_case()
        (case_dir / "plan.yaml").write_text(
            yaml.dump({"target": 1500, "options": [], "ladder": [],
                       "facts": []})
        )
        proc, out = self.gate(case_id, send_draft(template="hi"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("plan", out["error"])
        self.assertIn("limits", out["error"])

    def test_non_price_options_not_checked_against_floor(self):
        case_id, _ = self.make_case(
            plan={
                "target": 1000,
                "options": [
                    {"label": "cashback", "value": 2000,
                     "kind": "bonus", "terms": "signup credit"},
                    {"label": "convenience", "value": 2000,
                     "kind": "fee", "terms": "monthly"},
                    {"label": "annual", "value": 950, "kind": "price"},
                ],
                "ladder": [{"label": "anchor", "value": 1000}],
                "facts": [],
            }
        )
        proc, out = self.gate(
            case_id,
            send_draft(
                template="keep the {option:cashback} and "
                "{option:convenience}, price {option:annual}"
            ),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("$2,000", out["rendered"])
        self.assertIn("$950", out["rendered"])

    def test_unknown_option_kind_errors(self):
        case_id, _ = self.make_case(
            plan={
                "target": 1000,
                "options": [{"label": "mystery", "value": 2000,
                             "kind": "voucher"}],
                "ladder": [], "facts": [],
            }
        )
        proc, out = self.gate(case_id, send_draft(template="hi"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("kind", out["error"])

    def test_plan_different_period_not_checked(self):
        # floor is monthly (plan period "month"); a yearly option is a
        # different-period price, not a floor violation at plan-check
        # time. The render-time check still applies if it is quoted.
        case_id, _ = self.make_case(
            plan={
                "target": 1000,
                "period": "month",
                "options": [
                    {"label": "annual", "value": 15000,
                     "period": "year", "terms": "prepay"},
                ],
                "ladder": [],
                "facts": [],
            }
        )
        proc, out = self.gate(
            case_id, send_draft(period="month", template="hi")
        )
        self.assertEqual(proc.returncode, 0, out)

    def test_mode_case_insensitive(self):
        # mode "Coach" is still coach mode: every send needs approval.
        case_id, _ = self.make_case(brief={"mode": "Coach"})
        proc, out = self.gate(
            case_id, send_draft(template="hi")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("coach", " ".join(out["reasons"]).lower())
        case_id, _ = self.make_case(brief={"mode": "sideways"})
        proc, out = self.gate(case_id, send_draft(template="hi"))
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("mode", out["error"])

    def test_autonomy_string_rejected(self):
        case_id, _ = self.make_case(
            brief={"autonomy": "1 (draft only)"}
        )
        proc, out = self.gate(case_id, send_draft(template="hi"))
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)
        self.assertIn("autonomy", out["error"])

    def test_autonomy_out_of_range_rejected(self):
        for bad in (0, 5, True, 1.5):
            with self.subTest(autonomy=bad):
                case_id, _ = self.make_case(brief={"autonomy": bad})
                proc, out = self.gate(case_id, send_draft(template="hi"))
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("autonomy", out["error"])
        # Autonomy 1 is valid and means the user approves every send.
        case_id, _ = self.make_case(brief={"autonomy": 1})
        proc, out = self.gate(case_id, send_draft(template="hi"))
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("autonomy 1", " ".join(out["reasons"]))

    def test_case_id_traversal_rejected(self):
        for cid in ("../etc", "..", "a b", "UPPER", "x_y",
                    "with/slash", ""):
            with self.subTest(case_id=cid):
                proc, out = run_bt_json(self.home, "case", "show", cid)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("case id", out["error"].lower())
        proc, out = run_bt_json(self.home, "case", "show", "x" * 300)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_unexpected_exception_json(self):
        # Any unhandled exception must print {"error": ...} and exit 2,
        # never a traceback.
        case_id, _ = self.make_case()
        proc, out = run_bt_json(self.home, "gate", case_id,
                                "--draft", "/dev/null/x")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_unexpected_exception_in_process(self):
        # A crash inside a handler still comes out as {"error": ...}.
        import bt

        case_id, _ = self.make_case()
        path = write_draft(self.tmp, send_draft())
        original = bt.gate.check

        def boom(*a, **k):
            raise RuntimeError("synthetic crash")

        bt.gate.check = boom
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = bt.main(["gate", case_id, "--draft", str(path)])
        finally:
            bt.gate.check = original
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 2)
        self.assertIn("error", out)

    def test_cli_never_prints_traceback(self):
        case_id, _ = self.make_case()
        proc = run_bt(self.home, "gate", case_id,
                      "--draft", "/dev/null/x")
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
