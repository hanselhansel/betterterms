"""Step-2 review fixes (fail closed): a send offer whose period
cannot convert to the floor's skips the raw worse-than-floor
comparison and routes to the user, a null draft ``period`` reads as
"not set" like the plan, fact and inbound period keys, and a lone
surrogate or any unencodable character in a template or fact blocks
with exit 1 instead of crashing out as exit 2."""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    BtTestCase,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import yaml

LIMITS = "outside your limits; escalate to the user"
PERIOD_DIFFERS = "period differs from your limit"


class FailClosedCase(BtTestCase):
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


class UnconvertibleSendTest(FailClosedCase):
    def test_unconvertible_send_skips_raw_floor_comparison(self):
        # floor 1200 once, send 1300/month: the raw values are unlike
        # units (1300 > 1200 reads "worse" for pay), so the gate skips
        # the comparison and routes the send to the user (0010).
        case_id = self.make_case()
        draft = send_draft(
            offer=1300, period="month", template="I can do {offer}"
        )
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["reasons"], [PERIOD_DIFFERS])
        self.assertNotIn(LIMITS, out["reasons"])
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "I can do $1,300/month")

    def test_unconvertible_send_receive_direction_routes_too(self):
        # The mirror: a send offer below the once floor in a receive
        # case compares "worse" raw (1100 < 1200) and must still route
        # rather than block on unlike units.
        case_id = self.make_case(direction="receive")
        proc, out = self.gate(
            case_id,
            send_draft(
                offer=1100, period="month", template="I can do {offer}"
            ),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(PERIOD_DIFFERS, out["reasons"])

    def test_agreeing_actions_still_block_on_unconvertible(self):
        # Control: accept, sign and pay keep failing closed.
        case_id = self.make_case()
        for action in ("accept", "sign", "pay"):
            with self.subTest(action=action):
                kw = {"approved": True}
                if action == "accept":
                    kw["inbound"] = {
                        "offer": 1300, "period": "month",
                        "text": "x", "amounts": [],
                    }
                proc, out = self.gate(
                    case_id,
                    send_draft(
                        action=action, offer=1300, period="month",
                        template="let us close",
                    ),
                    **kw,
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(PERIOD_DIFFERS, out["reasons"])


class DraftPeriodTest(FailClosedCase):
    def test_null_draft_period_means_not_set(self):
        # ``period: null`` is "not set" and defaults to once, like the
        # plan, fact and inbound period keys; it never blocks as a
        # bad period string.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id,
            send_draft(period=None, template="I can do {offer}"),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "I can do $1,100")


class UnencodableCharTest(FailClosedCase):
    def test_lone_surrogate_in_template_blocks_not_errors(self):
        # A lone surrogate cannot encode to UTF-8: sizing it used to
        # die as UnicodeEncodeError (exit 2). It is a plain block.
        case_id = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(template="pay \ud800 now")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("unusual characters", " ".join(out["reasons"]))
        self.assertIsNone(out["rendered"])

    def test_lone_surrogate_in_fact_text_blocks_not_errors(self):
        plan = dict(
            plan_for("pay", 1200),
            facts=[{"id": "fs", "text": "x\ud800y", "source": "x"}],
        )
        case_id = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id, send_draft(template="see {fact:fs}")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("unusual characters", " ".join(out["reasons"]))


if __name__ == "__main__":
    unittest.main()
