"""Period fixes from the step-2 gate review: a rendered value equal
to the floor only after an x12 or /12 conversion is a review hit, not
a block; ``accept`` compares the inbound offer in the floor's
declared period; ``floor_period`` is the canonical plan key; and a
present period key validates even when another key shadows it."""

import unittest

from bt_helpers import (
    approve_held,
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
from btlib import yaml

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
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        if approved:
            args = approve_held(self.home, case_id, args)
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

    def test_five_years_routes_as_amount_and_as_text(self):
        # A rendered 5 against a 60/month floor is the floor /12 and
        # routes to the user; free-text "5 years" routes on its digits
        # too: the small-integer exception is gone.
        plan = dict(plan_for("pay", 60, target=50), period="month")
        case_id = self.make_case(floor=60, plan=plan)
        out = self.review(
            case_id,
            send_draft(offer=50, period="month",
                       template="term is {quote:1}"),
            inbound=inbound_msg(text="x", amounts=[5]),
        )
        self.assertIn("converted limit", " ".join(out["reasons"]))
        out = self.review(
            case_id,
            send_draft(offer=50, period="month",
                       template="every 5 years"),
        )
        self.assertIn("numbers", " ".join(out["reasons"]))


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

    def test_inbound_bad_period_errors(self):
        # An inbound file is parsed input like the plan and brief: a
        # present period naming no known period is a broken file,
        # exit 2, same as the score path, never a negotiation block.
        case_id = self.make_month_case()
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=60, period="month",
                       template="let us close it"),
            approved=True,
            inbound={"offer": 720, "period": "weekly", "text": "x",
                     "amounts": []},
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("inbound.yaml period: must be once, month or"
                      " year", out["error"])


class FloorPeriodKeyTest(PeriodCase):
    def test_floor_period_key_declares_the_floor_period(self):
        # ``floor_period`` is the canonical key; the legacy ``period``
        # key on the plan still works. A 720/year offer converts to
        # the 60/month floor exactly: inside the band, but on send it
        # is the walk-away number, so it routes to the user.
        for key in ("floor_period", "period"):
            with self.subTest(key=key):
                plan = dict(
                    plan_for("pay", 60, target=50), **{key: "month"}
                )
                case_id = self.make_case(floor=60, plan=plan)
                draft = send_draft(offer=720, period="year",
                                   template="I can do {offer}")
                proc, out = self.gate(case_id, draft)
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["rendered"], "I can do $720/year")
                self.assertIn(
                    "offer is at your limit", out["reasons"]
                )
                proc, out = self.gate(case_id, draft, approved=True)
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(out["rendered"], "I can do $720/year")

    # Extended by /ship coverage audit (pass 2): the ladder row.
    # Value: protects=an unrendered ladder entry with a bad period is a
    #   broken plan (exit 2), like a bad floor, option or fact period;
    # fails_when=check_plan_limits stops validating ladder periods, so the
    #   bad entry passes until some later draft renders it;
    # why_new=only floor, option and fact bad periods were pinned; seam=none
    def test_invalid_floor_period_exits_2(self):
        bad_ladder = [{"value": 1000, "reason": "r", "period": "weekly"}]
        for key, extra in (
            ("floor_period", {"floor_period": "weekly"}),
            ("period", {"period": "weekly"}),
            ("ladder", {"ladder": bad_ladder}),
        ):
            with self.subTest(key=key):
                plan = dict(plan_for("pay", 1200), **extra)
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(case_id, send_draft(template="hi"))
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("period", out["error"])

    def test_shadowed_period_still_validates(self):
        # A valid floor_period picks the floor's period; it must not
        # let a broken period key hide on the plan or the brief.
        for name, brief, plan in (
            (
                "plan",
                dict(BRIEF_PAY),
                dict(plan_for("pay", 1200), floor_period="month",
                     period="weekly"),
            ),
            (
                "brief",
                dict(BRIEF_PAY, period="weekly"),
                dict(plan_for("pay", 1200), floor_period="month"),
            ),
            (
                "brief behind plan",
                dict(BRIEF_PAY, period="weekly"),
                dict(plan_for("pay", 1200), period="month"),
            ),
        ):
            with self.subTest(name=name):
                case_id, case_dir = new_case(self.home)
                write_case_files(
                    case_dir, brief=brief, plan=plan, floor=1200,
                )
                proc, out = self.gate(
                    case_id, send_draft(template="hi")
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("period", out["error"])


class UnconvertiblePeriodTest(PeriodCase):
    """"once" and a recurring period have no conversion factor, so a
    mixed-period offer can never be verified against the floor: a
    ``send`` routes to the user, an agreeing action fails closed."""

    def test_send_monthly_offer_against_once_floor_needs_approval(self):
        # "{offer} per month" against a once floor cannot convert.
        case_id = self.make_case()
        draft = send_draft(
            offer=1100, period="month",
            template="I can do {offer} per month",
        )
        out = self.review(case_id, draft)
        self.assertIn(
            "period differs from your limit", out["reasons"]
        )
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            out["rendered"], "I can do $1,100/month per month"
        )

    def test_send_once_offer_against_month_floor_needs_approval(self):
        # The mirror: a one-time offer against a monthly floor.
        plan = dict(plan_for("pay", 1200), period="month")
        case_id = self.make_case(plan=plan)
        out = self.review(
            case_id,
            send_draft(offer=1100, period="once",
                       template="flat {offer}"),
        )
        self.assertIn(
            "period differs from your limit", out["reasons"]
        )

    def test_recurring_periods_still_convert(self):
        # month and year still convert to each other: only once
        # mixes route.
        plan = dict(plan_for("pay", 1200), period="month")
        case_id = self.make_case(plan=plan)
        self.passed(
            case_id,
            send_draft(offer=13000, period="year",
                       template="prepaid {offer}"),
        )

    def test_accept_monthly_offer_against_once_floor_blocks(self):
        # accept 1100/month against a 1100/year inbound, once floor:
        # neither side converts to once, so it fails closed.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=1100, period="month",
                       template="let us close"),
            approved=True,
            inbound={"offer": 1100, "period": "year", "text": "x",
                     "amounts": []},
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(
            "period differs from your limit", out["reasons"]
        )

    def test_accept_inbound_period_mismatch_blocks(self):
        # Draft offer matches the once floor, but the inbound offer
        # is per month against a once floor: unverifiable, so block.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=1100, period="once",
                       template="let us close"),
            approved=True,
            inbound={"offer": 1100, "period": "month", "text": "x",
                     "amounts": []},
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(
            "period differs from your limit", out["reasons"]
        )

    def test_sign_and_pay_mismatched_period_block(self):
        case_id = self.make_case()
        for action in ("sign", "pay"):
            with self.subTest(action=action):
                proc, out = self.gate(
                    case_id,
                    send_draft(action=action, offer=1100,
                               period="month",
                               template="let us close"),
                    approved=True,
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(
                    "period differs", " ".join(out["reasons"])
                )

    def test_matching_periods_do_not_route(self):
        # Control: an in-band monthly offer against a monthly floor
        # sends without the period reason.
        plan = dict(plan_for("pay", 1200), period="month")
        case_id = self.make_case(plan=plan)
        self.passed(
            case_id,
            send_draft(offer=1100, period="month",
                       template="I can do {offer}"),
        )


if __name__ == "__main__":
    unittest.main()
