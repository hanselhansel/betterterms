"""Widget fallback for cloud sessions (spec 6.8): ``bt.py widget``
prints a self-contained HTML fragment per view. The fragments carry
no document tags, escape every piece of case data, and call
``sendPrompt`` with the typed-command grammar. The terms widget shows
the walk-away as set or not set and never contains its value.
"""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    BtTestCase,
    plan_for,
    run_bt,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)

MAX_WIDGET = 64 * 1024
PRESS_ENTER = "Then press Enter to send."


class WidgetCase(BtTestCase):
    def make_case(self, name="bills-0001", floor=1200, plan=None):
        """A case with a deterministic id, so digit assertions never
        flake on a random case-id suffix."""
        case_dir = self.home / "cases" / name
        case_dir.mkdir(parents=True)
        (case_dir / "sources").mkdir()
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY),
            plan=plan if plan is not None else plan_for("pay", floor),
        )
        if floor is not None:
            proc, out = run_bt_json(
                self.home, "case", "set-floor", name, stdin=f"{floor}\n"
            )
            assert proc.returncode == 0, out
        return name, case_dir

    def hold_draft(self, case_id, draft):
        path = write_draft(self.tmp, draft)
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        assert proc.returncode == 3, out
        return out["hash"]

    def widget(self, *args):
        return run_bt_json(self.home, "widget", *args)


class TermsWidgetTest(WidgetCase):
    def test_terms_widget_never_contains_floor(self):
        # The walk-away enters only through the user's own typed
        # command: the widget reports set or not set and leaves the
        # field empty, so the value 62 appears nowhere in the html.
        case_id, _ = self.make_case(
            floor=62, plan=plan_for("pay", 62, target=50)
        )
        proc, out = self.widget("terms", case_id)
        self.assertEqual(proc.returncode, 0, out)
        html = out["html"]
        self.assertNotIn("62", html)
        self.assertIn("walk-away", html)
        self.assertIn("set", html)

    def test_terms_widget_reports_not_set(self):
        case_id, _ = self.make_case(floor=None)
        proc, out = self.widget("terms", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("not set", out["html"])

    def test_terms_widget_buttons_and_enter_hint(self):
        case_id, _ = self.make_case(floor=None)
        proc, out = self.widget("terms", case_id)
        self.assertEqual(proc.returncode, 0, out)
        html = out["html"]
        self.assertIn("sendPrompt(", html)
        self.assertIn(f"'bt terms {case_id}", html)
        self.assertIn(f"'bt floor {case_id}", html)
        self.assertIn(PRESS_ENTER, html)


class ApprovalWidgetTest(WidgetCase):
    def test_approval_widget_buttons(self):
        case_id, _ = self.make_case()
        draft = send_draft(
            action="cancel", offer=None, template="please end my plan"
        )
        h = self.hold_draft(case_id, draft)
        proc, out = self.widget("approval", case_id, h[:8])
        self.assertEqual(proc.returncode, 0, out)
        html = out["html"]
        self.assertIn(f"sendPrompt('bt approve {case_id} {h[:8]}')", html)
        self.assertIn(f"sendPrompt('bt reject {case_id} {h[:8]}')", html)
        self.assertIn("please end my plan", html)
        self.assertIn(PRESS_ENTER, html)

    def test_widget_escapes_text(self):
        case_id, _ = self.make_case()
        draft = send_draft(
            action="cancel",
            offer=None,
            template="pay <script>alert(1)</script> now",
        )
        h = self.hold_draft(case_id, draft)
        proc, out = self.widget("approval", case_id, h[:8])
        self.assertEqual(proc.returncode, 0, out)
        html = out["html"]
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_approval_unknown_hash_exits_2(self):
        case_id, _ = self.make_case()
        proc, out = self.widget("approval", case_id, "deadbeef")
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)


class CasesWidgetTest(WidgetCase):
    def test_cases_widget_lists_case(self):
        case_id, _ = self.make_case()
        proc, out = self.widget("cases")
        self.assertEqual(proc.returncode, 0, out)
        html = out["html"]
        self.assertIn(case_id, html)
        self.assertIn("bills", html)

    def test_cases_widget_shows_held_count(self):
        case_id, _ = self.make_case()
        self.hold_draft(
            case_id,
            send_draft(
                action="cancel", offer=None, template="please end my plan"
            ),
        )
        proc, out = self.widget("cases")
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("1", out["html"])


class SavingsWidgetTest(WidgetCase):
    def test_savings_widget_totals(self):
        case_id, _ = self.make_case()
        proc, out = run_bt_json(
            self.home,
            "ledger", "add", case_id,
            "--before", "90", "--after", "80", "--period", "month",
        )
        assert proc.returncode == 0, out
        proc, out = self.widget("savings")
        self.assertEqual(proc.returncode, 0, out)
        html = out["html"]
        self.assertIn("120", html)
        self.assertIn("saved", html)

    def test_savings_widget_shows_once_separately(self):
        # A one-time saving is never folded into the per-year figure:
        # it displays as its own "$N once" amount.
        c1, _ = self.make_case("bills-0001")
        c2, _ = self.make_case("bills-0002")
        for cid, before, after, period in (
            (c1, "90", "80", "month"),
            (c2, "1000", "900", "once"),
        ):
            proc, out = run_bt_json(
                self.home, "ledger", "add", cid,
                "--before", before, "--after", after,
                "--period", period,
            )
            assert proc.returncode == 0, out
        proc, out = self.widget("savings")
        self.assertEqual(proc.returncode, 0, out)
        html = out["html"]
        self.assertIn("120", html)
        self.assertIn("once", html)
        self.assertIn("100", html)


class WidgetShapeTest(WidgetCase):
    def all_widgets(self, case_id, h=None):
        yield self.widget("cases")
        yield self.widget("terms", case_id)
        yield self.widget("savings")
        if h is not None:
            yield self.widget("approval", case_id, h[:8])

    def test_widget_no_document_tags(self):
        case_id, _ = self.make_case()
        h = self.hold_draft(
            case_id,
            send_draft(
                action="cancel", offer=None, template="please end my plan"
            ),
        )
        for proc, out in self.all_widgets(case_id, h):
            self.assertEqual(proc.returncode, 0, out)
            html = out["html"].lower()
            for tag in ("<html", "<head", "<body"):
                self.assertNotIn(tag, html, out["html"][:200])

    def test_widget_size_under_64k(self):
        case_id, _ = self.make_case()
        h = self.hold_draft(
            case_id,
            send_draft(
                action="cancel", offer=None, template="please end my plan"
            ),
        )
        for proc, out in self.all_widgets(case_id, h):
            self.assertEqual(proc.returncode, 0, out)
            self.assertLess(len(out["html"]), MAX_WIDGET)

    def test_widget_usage_error_exits_2(self):
        proc = run_bt(self.home, "widget", "terms")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
