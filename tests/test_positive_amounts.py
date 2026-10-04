"""Non-positive amounts: a zero or negative amount is never a price.
Draft and inbound files report a block (exit 1); a broken plan or
brief exits 2. Every floor comparison reads positive values only, so
``-1200`` can never equal a 1200 floor nor slip inside a pay band.
"""

import unittest

from bt_helpers import (
    PriceCase,
    inbound_msg,
    plan_for,
    send_draft,
    write_case_files,
    new_case,
    BtTestCase,
    BRIEF_PAY,
)


class NonPositiveOfferTest(PriceCase):
    def test_negative_offer_against_equal_floor_blocks(self):
        # offer -1200 with a 1200 floor: the signed comparison hole
        # must never render nor pass. A negative offer is not an offer.
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(offer=-1200, template="we can do {offer}"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIsNone(out["rendered"])

    def test_zero_offer_blocks(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(case_id, send_draft(offer=0))
        self.assertEqual(proc.returncode, 1, out)
        self.assertIsNone(out["rendered"])

    def test_negative_offer_receive_direction_blocks(self):
        case_id = self.make_case(direction="receive", floor=150000)
        proc, out = self.gate(
            case_id,
            send_draft(offer=-1, template="i take {offer}"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIsNone(out["rendered"])

    def test_fractional_negative_offer_blocks(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(case_id, send_draft(offer=-0.01))
        self.assertEqual(proc.returncode, 1, out)
        self.assertIsNone(out["rendered"])


class NonPositivePlanTest(PriceCase):
    def _broken_plan(self, **over):
        return dict(plan_for("pay", 1200), **over)

    def test_negative_target_exits_2(self):
        case_id = self.make_case(floor=1200, plan=self._broken_plan(target=-500))
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 2, out)

    def test_zero_target_exits_2(self):
        case_id = self.make_case(floor=1200, plan=self._broken_plan(target=0))
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 2, out)

    def test_negative_price_option_exits_2(self):
        plan = self._broken_plan(
            options=[{"label": "a", "value": -5, "kind": "price"}]
        )
        case_id = self.make_case(floor=1200, plan=plan)
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 2, out)

    def test_negative_bonus_option_exits_2(self):
        # Bonus options skip the worse-than check but a negative
        # amount is still a broken plan.
        plan = self._broken_plan(
            options=[{"label": "b", "value": -1, "kind": "bonus"}]
        )
        case_id = self.make_case(floor=1200, plan=plan)
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 2, out)

    def test_negative_option_other_period_exits_2(self):
        # A negative value is broken even in a period the floor
        # cannot compare against.
        plan = self._broken_plan(
            period="month",
            options=[
                {"label": "a", "value": -5, "period": "year"}
            ],
        )
        case_id = self.make_case(floor=1200, plan=plan)
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 2, out)

    def test_negative_ladder_value_exits_2(self):
        plan = self._broken_plan(
            ladder=[{"value": -3, "reason": "r"}]
        )
        case_id = self.make_case(floor=1200, plan=plan)
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 2, out)

    def test_negative_fact_amount_exits_2(self):
        plan = self._broken_plan(
            facts=[{"id": "f9", "text": "x", "amount": -10}]
        )
        case_id = self.make_case(floor=1200, plan=plan)
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 2, out)

    def test_negative_target_score_exits_2(self):
        case_id = self.make_case(floor=1200, plan=self._broken_plan(target=-500))
        proc, out = self.score(case_id, inbound_msg(offer=1100))
        self.assertEqual(proc.returncode, 2, out)


class NonPositiveInboundTest(PriceCase):
    def test_negative_inbound_offer_blocks(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(template="counter?"),
            inbound=inbound_msg(offer=-600),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIsNone(out["rendered"])

    def test_zero_inbound_offer_blocks(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(template="counter?"),
            inbound=inbound_msg(offer=0),
        )
        self.assertEqual(proc.returncode, 1, out)

    def test_negative_inbound_amount_blocks(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(template="you said {quote:1}?"),
            inbound=inbound_msg(amounts=[-50]),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIsNone(out["rendered"])

    def test_negative_inbound_amount_unquoted_blocks(self):
        # Even unreferenced, a negative amounts entry is a broken
        # inbound file.
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(template="hi"),
            inbound=inbound_msg(amounts=[50, -1]),
        )
        self.assertEqual(proc.returncode, 1, out)

    def test_negative_inbound_offer_score_blocks(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.score(case_id, inbound_msg(offer=-600))
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")

    def test_negative_inbound_amount_score_blocks(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.score(case_id, inbound_msg(amounts=[-5]))
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")


class PositiveAmountsUnaffectedTest(PriceCase):
    def test_normal_offer_and_inbound_still_pass(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(offer=1100, template="we can do {offer}"),
            inbound=inbound_msg(offer=1050, amounts=[1050]),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")


if __name__ == "__main__":
    unittest.main()
