"""Floor-in-rendered-text rule (spec 4 follow-up): structured checks
compare placeholder values only, but fact bodies, verbatim string
quotes and literal template words all reach the wire, so the final
rendered text is scanned with ``money.find`` and any amount equal to
the floor hard-blocks with a plain reason that names no number. The
one exception is the draft's own ``{offer}`` output when the offer
itself sits at the floor: existing at-limit rules already route that
send, and approving it is the user's call.
"""

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
from btlib import yaml

WALK_AWAY = "the message contains your walk-away amount"


class FloorInTextCase(BtTestCase):
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

    def assert_walk_away_block(self, proc, out):
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn(WALK_AWAY, out["reasons"])
        self.assertIsNone(out["rendered"])
        self.assertFalse(
            any(
                any(c.isdigit() for c in r) for r in out["reasons"]
            ),
            out["reasons"],
        )


class FloorInTextTest(FloorInTextCase):
    def test_fact_text_with_floor_blocks(self):
        # evals/fixtures/cases/job-offer regression: fact f1's text
        # carries the floor inside a posted range even though its
        # structured amount is the range top.
        plan = dict(
            plan_for("receive", 150000),
            floor_period="year",
            facts=[
                {
                    "id": "f1",
                    "text": "posted range for this role is $150,000 "
                    "to $190,000 base",
                    "source": "listing",
                    "amount": 190000,
                    "period": "year",
                },
            ],
        )
        case_id = self.make_case(
            direction="receive", floor=150000, plan=plan
        )
        proc, out = self.gate(
            case_id,
            send_draft(
                offer=180000,
                period="year",
                template="The {fact:f1}. Can we discuss {offer}?",
            ),
        )
        self.assert_walk_away_block(proc, out)

    def test_string_quote_with_floor_blocks(self):
        # A string amounts entry renders verbatim, so no structured
        # value ever sees the floor written inside it.
        plan = dict(plan_for("receive", 150000), floor_period="year")
        case_id = self.make_case(
            direction="receive", floor=150000, plan=plan
        )
        proc, out = self.gate(
            case_id,
            send_draft(
                offer=180000,
                period="year",
                template="you wrote {quote:1}",
            ),
            inbound=inbound_msg(amounts=["we can do 150,000"]),
        )
        self.assert_walk_away_block(proc, out)

    def test_offer_equal_floor_still_allowed(self):
        # The draft's own {offer} at the floor is exempt: a send at
        # the walk-away routes to the user like before and ships on
        # approval.
        case_id = self.make_case(direction="pay", floor=150000)
        draft = send_draft(
            offer=150000, template="I can do {offer} today"
        )
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertNotIn(WALK_AWAY, out["reasons"])
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            out["rendered"], "I can do $150,000 today"
        )

    def test_floor_in_other_period_blocks(self):
        # "$100 a month" against a 1200/year floor states the floor
        # after conversion; it blocks like the as-written form.
        plan = dict(plan_for("pay", 1200), floor_period="year")
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(
                offer=1100,
                period="year",
                template="we can pay $100 a month",
            ),
        )
        self.assert_walk_away_block(proc, out)


if __name__ == "__main__":
    unittest.main()
