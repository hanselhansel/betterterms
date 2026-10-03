"""Period and numeric-bound fixes from the step-2 gate review: a
rendered value equal to the floor only after an x12 or /12 conversion
is a review hit, not a block; ``accept`` compares the inbound offer in
the floor's declared period; ``floor_period`` is the canonical plan
key; and cases.num caps magnitudes at 1e12."""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    BtTestCase,
    inbound_msg,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import cases, yaml

LIMITS = "outside your limits; escalate to the user"


class PeriodCase(BtTestCase):
    def make_case(self, direction="pay", floor=1200, plan=None):
        case_id, case_dir = new_case(self.home, direction=direction)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, direction=direction),
            plan=plan_for(direction, floor) if plan is None else plan,
            floor=floor,
        )
        return case_id

    def gate(self, case_id, draft, approved=False, inbound=None):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if approved:
            args.append("--approved")
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        return run_bt_json(self.home, *args)

    def review(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        return out

    def passed(self, case_id, draft, **kw):
        proc, out = self.gate(case_id, draft, **kw)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")
        return out


class ConvertedLimitTest(PeriodCase):
    def test_exact_floor_render_still_blocks(self):
        # Control: a rendered value equal to the floor hard blocks.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(template="you said {quote:1}"),
            inbound=inbound_msg(text="x", amounts=[1200]),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["reasons"], [LIMITS])

    def test_converted_floor_render_needs_approval_not_block(self):
        # floor 1200/month: a rendered 14400 (x12) or 100 (/12) routes
        # to the user with a number-free reason; it no longer blocks,
        # and an explicit yes still sends it.
        plan = dict(plan_for("pay", 1200), period="month")
        case_id = self.make_case(plan=plan)
        for amounts in ([14400], [100]):
            with self.subTest(amounts=amounts):
                out = self.review(
                    case_id,
                    send_draft(template="you said {quote:1}"),
                    inbound=inbound_msg(text="x", amounts=amounts),
                )
                self.assertIn(
                    "converted limit", " ".join(out["reasons"])
                )
                self.assertFalse(
                    any(any(c.isdigit() for c in r)
                        for r in out["reasons"])
                )
                proc, out = self.gate(
                    case_id,
                    send_draft(template="you said {quote:1}"),
                    approved=True,
                    inbound=inbound_msg(text="x", amounts=amounts),
                )
                self.assertEqual(proc.returncode, 0, out)

    def test_five_years_needs_approval_only_as_rendered_amount(self):
        # The review probe: a rendered 5 against a 60/month floor is
        # the floor /12 and routes to the user; free-text "5 years" is
        # a small integer and passes.
        plan = dict(plan_for("pay", 60, target=50), period="month")
        case_id = self.make_case(floor=60, plan=plan)
        out = self.review(
            case_id,
            send_draft(offer=50, template="term is {quote:1}"),
            inbound=inbound_msg(text="x", amounts=[5]),
        )
        self.assertIn("converted limit", " ".join(out["reasons"]))
        self.passed(case_id, send_draft(offer=50,
                                        template="every 5 years"))


class AcceptConversionTest(PeriodCase):
    def make_month_case(self):
        plan = dict(plan_for("pay", 60, target=50), floor_period="month")
        return self.make_case(floor=60, plan=plan)

    def test_accept_converts_inbound_to_floor_period(self):
        # floor 60/month, inbound 720/year is in-band: it equals the
        # floor after conversion and a matching draft offer accepts.
        case_id = self.make_month_case()
        inbound = {"offer": 720, "period": "year", "text": "x",
                   "amounts": []}
        for offer, period in ((60, "month"), (720, "year")):
            with self.subTest(offer=offer, period=period):
                proc, out = self.gate(
                    case_id,
                    send_draft(action="accept", offer=offer,
                               period=period,
                               template="let us close it"),
                    approved=True,
                    inbound=inbound,
                )
                self.assertEqual(proc.returncode, 0, out)
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=55, period="month",
                       template="let us close it"),
            approved=True,
            inbound=inbound,
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("accept must equal", " ".join(out["reasons"]))

    def test_accept_inbound_period_defaults_to_floor_period(self):
        # No inbound period: the offer reads in the floor's period.
        case_id = self.make_month_case()
        inbound = {"offer": 60, "text": "x", "amounts": []}
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=720, period="year",
                       template="let us close it"),
            approved=True,
            inbound=inbound,
        )
        self.assertEqual(proc.returncode, 0, out)

    def test_accept_inbound_worse_than_floor_blocks(self):
        # 840/year is 70/month, worse than the 60/month floor.
        case_id = self.make_month_case()
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=70, period="month",
                       template="let us close it"),
            approved=True,
            inbound={"offer": 840, "period": "year", "text": "x",
                     "amounts": []},
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_inbound_bad_period_blocks(self):
        case_id = self.make_month_case()
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=60, period="month",
                       template="let us close it"),
            approved=True,
            inbound={"offer": 720, "period": "weekly", "text": "x",
                     "amounts": []},
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("period must be once, month or year",
                      " ".join(out["reasons"]))


class FloorPeriodKeyTest(PeriodCase):
    def test_floor_period_key_declares_the_floor_period(self):
        # ``floor_period`` is the canonical key; the legacy ``period``
        # key on the plan still works.
        for key in ("floor_period", "period"):
            with self.subTest(key=key):
                plan = dict(
                    plan_for("pay", 60, target=50), **{key: "month"}
                )
                case_id = self.make_case(floor=60, plan=plan)
                proc, out = self.gate(
                    case_id,
                    send_draft(offer=720, period="year",
                               template="I can do {offer}"),
                )
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(out["rendered"], "I can do $720/year")

    def test_invalid_floor_period_exits_2(self):
        for key in ("floor_period", "period"):
            with self.subTest(key=key):
                plan = dict(plan_for("pay", 1200), **{key: "weekly"})
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(case_id, send_draft(template="hi"))
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("period", out["error"])


class NumCapTest(PeriodCase):
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
