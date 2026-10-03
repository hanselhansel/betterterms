"""Unconvertible-period price values and strict period keys
(adversarial review fixes): a price option or ladder value whose
period cannot be converted to the floor's declared period blocks when
rendered, matching the offer rule; bonus and fee options keep their
equality-only treatment. A period key that is present but not a
string, or names no known period, is a broken plan (exit 2): the
default applies only when the key is absent.
"""

import unittest

from bt_helpers import (
    PriceCase,
    inbound_msg,
    plan_for,
    send_draft,
)

LIMITS = "outside your limits; escalate to the user"


class UnconvertiblePriceTest(PriceCase):
    def test_monthly_price_option_against_once_floor_blocks(self):
        # floor 100 once; an option priced 80/month can never convert,
        # so rendering it blocks like an unconvertible offer does.
        plan = dict(
            plan_for("pay", 100, target=80),
            options=[
                {"label": "monthly", "value": 80, "kind": "price",
                 "period": "month"},
            ],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=None, template="how about {option:monthly}")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn(
            "period differs from your limit", out["reasons"]
        )
        self.assertIsNone(out["rendered"])

    def test_once_option_against_month_floor_blocks(self):
        # The mirror: a flat option against a monthly floor.
        plan = dict(
            plan_for("pay", 100, target=80),
            period="month",
            options=[
                {"label": "flat", "value": 80, "kind": "price",
                 "period": "once"},
            ],
            ladder=[{"value": 95, "reason": "r", "period": "month"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(offer=None, period="month",
                                template="a {option:flat} plan")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(
            "period differs from your limit", out["reasons"]
        )

    def test_ladder_value_unconvertible_blocks(self):
        plan = dict(
            plan_for("pay", 100, target=80),
            ladder=[{"value": 80, "reason": "r", "period": "month"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(offer=None, template="pushed: {ladder:1}")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(
            "period differs from your limit", out["reasons"]
        )

    def test_unconvertible_price_blocks_on_agreeing_actions(self):
        # The rule is a hard block on every action, not only send.
        plan = dict(
            plan_for("pay", 100, target=80),
            options=[
                {"label": "monthly", "value": 80, "kind": "price",
                 "period": "month"},
            ],
        )
        case_id = self.make_case(plan=plan)
        for action in ("accept", "sign", "pay"):
            with self.subTest(action=action):
                kw = {"approved": True}
                if action == "accept":
                    kw["inbound"] = inbound_msg(offer=90, text="x")
                proc, out = self.gate(
                    case_id,
                    send_draft(action=action, offer=90,
                               template="at {option:monthly}"),
                    **kw,
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(
                    "period differs", " ".join(out["reasons"])
                )

    def test_quote_and_fact_unconvertible_block_off_send(self):
        # Quotes and facts keep their send exemption, but on agreeing
        # actions an unconvertible rendered value fails closed too.
        plan = dict(
            plan_for("pay", 100, target=80),
            period="month",
            facts=[{"id": "f1", "text": "they asked flat",
                    "source": "x", "amount": 90}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(action="sign", offer=90, period="month",
                       template="their ask was {fact:f1}"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("period differs", " ".join(out["reasons"]))
        proc, out = self.gate(
            case_id,
            send_draft(action="pay", offer=90, period="month",
                       template="you said {quote:1}"),
            approved=True,
            inbound=inbound_msg(text="x", amounts=[90]),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("period differs", " ".join(out["reasons"]))

    def test_send_quote_exemption_still_holds(self):
        # Documented carve-out: a send may quote a counterparty value
        # worse than the floor, including one it cannot convert.
        plan = dict(plan_for("pay", 100, target=80), period="month")
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=90, period="month",
                       template="you said {quote:1}"),
            inbound=inbound_msg(text="x", amounts=[50]),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("$50", out["rendered"])

    def test_bonus_fee_unconvertible_period_still_renders(self):
        # Bonus and fee options are not offers: an unconvertible
        # period does not block them; equality still applies.
        plan = dict(
            plan_for("pay", 100, target=80),
            options=[
                {"label": "credit", "value": 80, "kind": "bonus",
                 "period": "month"},
            ],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=None, template="keep the {option:credit}")
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("$80/month", out["rendered"])

    def test_convertible_periods_still_checked(self):
        # Control: a yearly option against a monthly floor converts,
        # and a worse converted value still blocks.
        plan = dict(
            plan_for("pay", 100, target=80),
            period="month",
            options=[
                {"label": "annual", "value": 1500, "kind": "price",
                 "period": "year"},
            ],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=90, period="month",
                       template="the {option:annual}"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])


class PresentPeriodTest(PriceCase):
    def test_present_non_string_periods_exit_2(self):
        # ``period`` present but not a string is a broken plan, never
        # a silent default: 0, false and a list all used to collapse
        # to the default through ``or``.
        bad_facts = [
            {"id": "f1", "text": "x", "source": "x", "period": bad}
            for bad in (0, False, ["month"], {"p": "month"})
        ]
        for fact in bad_facts:
            with self.subTest(period=repr(fact["period"])):
                plan = dict(plan_for("pay", 100, target=80), facts=[fact])
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(
                    case_id, send_draft(template="hi")
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("period", out["error"])

    def test_present_unknown_string_periods_exit_2(self):
        # An empty or unknown period string present on a fact is a
        # broken plan too; only an absent key defaults to once.
        for bad in ("", "weekly", "MONTHLY"):
            with self.subTest(period=repr(bad)):
                plan = dict(
                    plan_for("pay", 100, target=80),
                    facts=[{"id": "f1", "text": "x", "source": "x",
                            "period": bad}],
                )
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(
                    case_id, send_draft(template="hi")
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("period", out["error"])

    def test_present_bad_option_ladder_plan_periods_exit_2(self):
        for extra in (
            {"options": [{"label": "x", "value": 50, "period": 0}]},
            {"ladder": [{"value": 50, "reason": "r", "period": False}]},
            {"period": 0},
            {"period": ""},
            {"floor_period": []},
        ):
            with self.subTest(extra=repr(extra)[:60]):
                plan = dict(plan_for("pay", 100, target=80), **extra)
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(
                    case_id, send_draft(template="hi")
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("period", out["error"])

    def test_absent_period_still_defaults(self):
        # Control: no period key anywhere reads as once and works.
        plan = dict(
            plan_for("pay", 100, target=80),
            facts=[{"id": "f1", "text": "flat quote", "source": "x",
                    "amount": 90}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(action="sign", offer=95, template="it is {fact:f1}"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 0, out)


if __name__ == "__main__":
    unittest.main()
