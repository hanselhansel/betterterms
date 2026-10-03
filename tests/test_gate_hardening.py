"""Gate hardening: the every-amount floor rule, oracle-free block
reasons, the coach/approval gate, the text size cap and plan and
direction validation."""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    PLAN_BILLS,
    BtTestCase,
    new_case,
    plan_for,
    run_bt_json,
    write_case_files,
    write_draft,
)
from btlib import yaml

LIMITS = "outside your limits; escalate to the user"
OFFERED = ("accept", "pay", "sign")


class GateHardeningTest(BtTestCase):
    def make_case(self, direction="pay", floor=1200, brief=None, plan=None):
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

    def score(self, case_id, inbound):
        path = self.tmp / "inbound.yaml"
        path.write_text(yaml.dump(inbound))
        return run_bt_json(self.home, "score", case_id, "--inbound", str(path))

    def send(self, **kw):
        d = {"action": "send", "offer": 1100, "text": "hi", "claims": []}
        d.update(kw)
        return d

    # K: every irreversible action needs --approved, then passes.
    def test_irreversible_actions_table(self):
        case_id = self.make_case()
        for action in ("accept", "cancel", "pay", "sign", "dispute"):
            with self.subTest(action=action):
                d = {
                    "action": action,
                    "offer": 1100 if action in OFFERED else None,
                    "text": "ok",
                    "claims": [],
                }
                proc, out = self.gate(case_id, d)
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")
                proc, out = self.gate(case_id, d, approved=True)
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(out["result"], "pass")

    # E: every floor-related block uses the one generic reason and
    # never carries the floor, a direction hint or a distance.
    def test_floor_blocks_are_generic_and_oracle_free(self):
        case_id = self.make_case()
        rows = [
            self.send(offer=1250),
            self.send(text="my max is $1,200"),
            self.send(text="twelve hundred is the cap"),
            self.send(text="order 1200 today"),
            self.send(text="I could pay $1,300"),
            {"action": "accept", "offer": None, "text": "ok", "claims": []},
        ]
        for draft in rows:
            with self.subTest(draft=draft):
                proc, out = self.gate(case_id, draft, approved=True)
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(LIMITS, out["reasons"])
                for reason in out["reasons"]:
                    self.assertNotIn("1200", reason)
                    self.assertNotIn("floor", reason.lower())
                    self.assertNotIn("receive", reason.lower())
                    self.assertNotIn("pay ", reason.lower())

    # C: a marked amount beyond the floor blocks in both directions.
    def test_marked_amount_beyond_floor_blocks(self):
        case_id = self.make_case()
        proc, out = self.gate(
            case_id, self.send(text="I could pay $1,300")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

        case_id = self.make_case(direction="receive", floor=150000)
        proc, out = self.gate(
            case_id,
            self.send(offer=160000, text="I would take $140,000"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    # C: quoting the counterparty's own amount passes only when the
    # draft's numeric offer is inside the band.
    def test_quoted_amount_passes_only_with_inband_offer(self):
        case_id = self.make_case()
        inbound = {"offer": 1300, "text": "we can do $1,300"}
        draft = self.send(text="your $1,300 is too high")
        proc, out = self.gate(case_id, draft, inbound=inbound)
        self.assertEqual(proc.returncode, 0, out)

        proc, out = self.gate(
            case_id, dict(draft, offer=None), inbound=inbound
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

        proc, out = self.gate(
            case_id, dict(draft, offer=1300), inbound=inbound
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    # C: accept, sign and pay require a numeric offer inside the band.
    def test_offered_actions_need_numeric_inband_offer(self):
        case_id = self.make_case()
        for action in OFFERED:
            for offer in (None, 1300):
                with self.subTest(action=action, offer=offer):
                    d = {"action": action, "offer": offer,
                         "text": "ok", "claims": []}
                    proc, out = self.gate(case_id, d, approved=True)
                    self.assertEqual(proc.returncode, 1, out)
                    self.assertIn(LIMITS, out["reasons"])
            with self.subTest(action=action, offer=1100):
                d = {"action": action, "offer": 1100,
                     "text": "ok", "claims": []}
                proc, out = self.gate(case_id, d, approved=True)
                self.assertEqual(proc.returncode, 0, out)

    # C: cancel and dispute carry no offer requirement.
    def test_cancel_and_dispute_need_no_offer(self):
        case_id = self.make_case()
        for action in ("cancel", "dispute"):
            with self.subTest(action=action):
                d = {"action": action, "offer": None,
                     "text": "done", "claims": []}
                proc, out = self.gate(case_id, d, approved=True)
                self.assertEqual(proc.returncode, 0, out)

    # C: an inbound offer worse than the floor cannot be accepted.
    def test_worse_inbound_offer_cannot_be_accepted(self):
        case_id = self.make_case()
        draft = {"action": "accept", "offer": 1100,
                 "text": "deal", "claims": []}
        proc, out = self.gate(
            case_id, draft, approved=True,
            inbound={"offer": 1300, "text": "final offer $1,300"},
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

        proc, out = self.gate(
            case_id, draft, approved=True,
            inbound={"offer": 1100, "text": "we can do $1,100"},
        )
        self.assertEqual(proc.returncode, 0, out)

    # D: the floor's digit string as a whole number token blocks, even
    # beside characters the money parser cannot read. A longer digit
    # run that merely contains the floor does not block.
    def test_floor_digit_string_blocks(self):
        case_id = self.make_case()
        for text in ("call 555-1200", "note 1200 thanks"):
            with self.subTest(text=text):
                proc, out = self.gate(case_id, self.send(text=text))
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(LIMITS, out["reasons"])
        for text in ("ref 120099", "around 1100 or so"):
            with self.subTest(text=text):
                proc, out = self.gate(case_id, self.send(text=text))
                self.assertEqual(proc.returncode, 0, out)

    # D: the floor scan matches whole number tokens, not substrings:
    # separators join only 3-digit groups, so "1 200" still leaks the
    # floor while longer runs and unrelated numbers pass. Marked
    # amounts above a pay floor need the quoting path to pass at all,
    # so $11,200 and $150 ride the counterparty's own inbound.
    def test_floor_digit_token_not_substring(self):
        case_id = self.make_case()
        inbound = {"offer": 11200, "text": "our invoice is $11,200"}
        for text in ("the invoice $11,200", "ref 312005",
                     "about 12000 requests", "see page 120"):
            with self.subTest(text=text):
                proc, out = self.gate(
                    case_id, self.send(text=text), inbound=inbound
                )
                self.assertEqual(proc.returncode, 0, out)
                self.assertEqual(out["result"], "pass")
        for text in ("the number 1 200 exactly", "it reads 1.200",
                     "the cap is 1'200", "note 1200 thanks",
                     "the cap is 1\u00a0200"):
            with self.subTest(text=text):
                proc, out = self.gate(case_id, self.send(text=text))
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(LIMITS, out["reasons"])

        case_id = self.make_case(floor=50, plan=plan_for("pay", 50, target=40))
        for text, inbound in (
            ("option $150 stays", {"offer": 150, "text": "flat $150"}),
            ("room 50", None),
        ):
            with self.subTest(text=text):
                proc, out = self.gate(
                    case_id,
                    {"action": "send", "offer": 45,
                     "text": text, "claims": []},
                    inbound=inbound,
                )
                if inbound is None:
                    self.assertEqual(proc.returncode, 1, out)
                    self.assertIn(LIMITS, out["reasons"])
                else:
                    self.assertEqual(proc.returncode, 0, out)
                    self.assertEqual(out["result"], "pass")

    # G: draft or inbound text over 64 KB blocks as too long.
    def test_message_too_long_blocks(self):
        case_id = self.make_case()
        over = "x" * (64 * 1024 + 1)
        proc, out = self.gate(case_id, self.send(text=over))
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("message too long", out["reasons"])

        proc, out = self.gate(
            case_id, self.send(), inbound={"offer": None, "text": over}
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("message too long", out["reasons"])

        proc, out = self.gate(
            case_id, self.send(text="x" * (64 * 1024))
        )
        self.assertEqual(proc.returncode, 0, out)

    # I: coach mode or autonomy 1 turns any send into needs_approval.
    def test_coach_mode_and_autonomy1_need_approval(self):
        for brief in ({"mode": "coach"}, {"autonomy": 1}):
            with self.subTest(brief=brief):
                case_id = self.make_case(brief=brief)
                proc, out = self.gate(case_id, self.send())
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")
                proc, out = self.gate(case_id, self.send(), approved=True)
                self.assertEqual(proc.returncode, 0, out)

    # F: plan values worse than the floor exit 2 in gate and score.
    def test_plan_conflicts_with_limits_exit_2(self):
        bad_plans = [
            dict(PLAN_BILLS, target=1300),
            dict(PLAN_BILLS,
                 options=[{"label": "x", "value": 1300, "terms": "y"}]),
            dict(PLAN_BILLS,
                 ladder=[{"value": 1300, "reason": "r"}]),
        ]
        for plan in bad_plans:
            with self.subTest(plan=plan):
                case_id = self.make_case(plan=plan)
                proc, out = self.gate(case_id, self.send())
                self.assertEqual(proc.returncode, 2, out)
                self.assertEqual(
                    out["error"], "plan conflicts with your limits"
                )
                proc, out = self.score(
                    case_id, {"offer": 1100, "text": "hi"}
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertEqual(
                    out["error"], "plan conflicts with your limits"
                )

        case_id = self.make_case(
            direction="receive", floor=150000,
            plan=dict(PLAN_BILLS, target=140000),
        )
        proc, out = self.gate(case_id, self.send(offer=160000))
        self.assertEqual(proc.returncode, 2, out)
        proc, out = self.score(case_id, {"offer": 160000, "text": "hi"})
        self.assertEqual(proc.returncode, 2, out)

    # F: brief direction must be pay or receive.
    def test_direction_must_be_pay_or_receive(self):
        for direction in ("sideways", "", None):
            with self.subTest(direction=direction):
                case_id, case_dir = new_case(self.home)
                b = dict(BRIEF_PAY)
                if direction is None:
                    del b["direction"]
                else:
                    b["direction"] = direction
                write_case_files(
                    case_dir, brief=b, plan=dict(PLAN_BILLS), floor=1200
                )
                proc, out = self.gate(case_id, self.send())
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)
                proc, out = self.score(
                    case_id, {"offer": 1100, "text": "hi"}
                )
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)

    # E: the untraced-number reason names no amount, so a blocked
    # draft can never echo the floor back through it.
    def test_untraced_reason_carries_no_value(self):
        case_id = self.make_case(plan={**PLAN_BILLS, "facts": []})
        proc, out = self.gate(
            case_id, self.send(text="not $55, not $77 either")
        )
        self.assertEqual(proc.returncode, 1, out)
        untraced = [r for r in out["reasons"] if "untraced number" in r]
        self.assertEqual(untraced, ["untraced number in draft text"])
        for reason in out["reasons"]:
            self.assertNotIn("55", reason)
            self.assertNotIn("77", reason)

    # D: numeric never_disclose items are normalized through money
    # parsing, so "1200" also catches "1.2k" and "$1,200".
    def test_never_disclose_numeric_normalized(self):
        case_id = self.make_case(brief={"never_disclose": ["1300"]})
        proc, out = self.gate(case_id, self.send(text="about $1,300"))
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(
            "never-disclose term appears in draft text", out["reasons"]
        )
        proc, out = self.gate(case_id, self.send(text="about $1,400"))
        self.assertNotIn(
            "never-disclose term appears in draft text", out["reasons"]
        )

        case_id = self.make_case(brief={"never_disclose": ["1400"]})
        proc, out = self.gate(
            case_id, self.send(text="I can do 1.4k", offer=1100)
        )
        self.assertIn(
            "never-disclose term appears in draft text", out["reasons"]
        )


if __name__ == "__main__":
    unittest.main()
