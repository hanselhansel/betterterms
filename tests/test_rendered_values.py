"""Rendered-value comparisons (adversarial review fixes): every limit
comparison reads the value as it renders, rounded to the currency
minor unit (two decimals), so a rendered amount can never land past
the floor inside the raw tolerance. The scorer reads the inbound
offer in its own period with the gate's conversion rules, and an
unconvertible period bands unknown and escalates.
"""

import unittest

from bt_helpers import PriceCase, plan_for, send_draft

LIMITS = "outside your limits; escalate to the user"
REVIEW = "a value in this draft needs your review"


class RenderedValueTest(PriceCase):
    def make_render_case(self, floor=100, plan=None):
        return self.make_case(
            floor=floor,
            plan=plan or plan_for("pay", floor, target=floor - 20),
        )

    def test_offer_converted_dust_routes_at_limit(self):
        # floor 1200/year; an offer of 100.004/month renders
        # "$100.00/month" and converts to exactly 1200/year: a send
        # routes to the generic review reason. The raw value used to
        # convert to 1200.048 and block as worse than the floor.
        plan = dict(plan_for("pay", 1200), period="year")
        case_id = self.make_render_case(floor=1200, plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=100.004, period="month",
                       template="my best is {offer}"),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])
        self.assertNotIn("limit", " ".join(out["reasons"]))
        self.assertEqual(out["rendered"], "my best is $100.00/month")

    def test_offer_rounding_on_floor_routes_at_limit(self):
        # 100.005 renders "$100.00": the rendered amount IS the floor,
        # so a send routes to the generic review reason, never blocks.
        case_id = self.make_render_case()
        proc, out = self.gate(
            case_id,
            send_draft(offer=100.005, template="my best is {offer}"),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(REVIEW, out["reasons"])
        self.assertNotIn("limit", " ".join(out["reasons"]))
        self.assertEqual(out["rendered"], "my best is $100.00")

    def test_rendered_amount_past_floor_blocks(self):
        # 100.006 renders "$100.01": a rendered amount past the floor
        # can never slip through as "at the limit" or "in band".
        case_id = self.make_render_case()
        proc, out = self.gate(
            case_id, send_draft(offer=100.006, template="counter")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_option_rounded_onto_floor_blocks_as_equal(self):
        # An option value of 100.004 renders "$100.00" = the floor:
        # a rendered non-offer value equal to the floor still blocks.
        plan = dict(
            plan_for("pay", 100, target=80),
            options=[{"label": "basic", "value": 100.004,
                      "kind": "price"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(offer=None,
                               template="the {option:basic} tier")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_option_rounded_below_floor_not_at_limit(self):
        # An option value of 99.994 renders "$99.99": inside the band
        # and not equal to the floor.
        plan = dict(
            plan_for("pay", 100, target=80),
            options=[{"label": "basic", "value": 99.994,
                      "kind": "price"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(offer=None,
                               template="the {option:basic} tier")
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("$99.99", out["rendered"])

    def test_plan_check_compares_rendered_values(self):
        # A plan target of 100.004 renders "$100.00" at the floor:
        # not a plan conflict (exit 2); rendering it blocks as equal.
        plan = dict(plan_for("pay", 100, target=100.004))
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(offer=None, template="aim {target}")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])


class ScorePeriodTest(PriceCase):
    def make_score_case(self, floor=60, target=50, period="month"):
        plan = dict(
            plan_for("pay", floor, target), floor_period=period
        )
        return self.make_case(floor=floor, plan=plan)

    def test_inbound_year_offer_converts_to_floor_period(self):
        # floor 60/month: inbound 720/year converts to 60/month, so it
        # bands near the floor instead of below it on the raw 720.
        case_id = self.make_score_case()
        proc, out = self.score(
            case_id, {"offer": 720, "period": "year", "text": "x"}
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["band"], "near_floor")
        proc, out = self.score(
            case_id, {"offer": 540, "period": "year", "text": "x"}
        )
        self.assertEqual(out["band"], "at_or_above_target")
        proc, out = self.score(
            case_id, {"offer": 840, "period": "year", "text": "x"}
        )
        self.assertEqual(out["band"], "below_floor")

    def test_inbound_same_period_unchanged(self):
        # Control: a monthly offer just inside the monthly floor.
        case_id = self.make_score_case()
        proc, out = self.score(
            case_id, {"offer": 59, "period": "month", "text": "x"}
        )
        self.assertEqual(out["band"], "near_floor")

    def test_inbound_bad_period_exits_2(self):
        case_id = self.make_score_case()
        proc, out = self.score(
            case_id, {"offer": 60, "period": "weekly", "text": "x"}
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("period", out["error"])

    def test_unconvertible_inbound_period_scores_unknown(self):
        # A once floor cannot verify a monthly offer: the band is
        # unknown and the turn escalates, never a raw-unit guess.
        case_id = self.make_case(
            floor=100, plan=plan_for("pay", 100, target=80)
        )
        proc, out = self.score(
            case_id, {"offer": 50, "period": "month", "text": "x"}
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["band"], "unknown")
        self.assertIn("offer_period_differs", out["escalate"])


if __name__ == "__main__":
    unittest.main()
