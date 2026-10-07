"""Gate verdicts for agreeing actions: accept, sign and pay run under
the structured-amounts contract, need the counterparty's offer, and
stay in band at the floor once approved.
"""

import unittest

from bt_helpers import (
    approve_held,
    BRIEF_PAY,
    PLAN_BILLS,
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


class GateActionTest(BtTestCase):
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
        return case_id, case_dir

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

    def test_irreversible_action_needs_approval(self):
        case_id, _ = self.make_case(floor=1200)
        draft = send_draft(action="accept", offer=1100,
                           template="sounds good to me")
        proc, out = self.gate(
            case_id, draft,
            inbound=inbound_msg(offer=1100, text="we can do $1,100",
                                amounts=[1100]),
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertEqual(out["rendered"], "sounds good to me")

    def test_irreversible_action_approved_passes(self):
        case_id, _ = self.make_case(floor=1200)
        draft = send_draft(action="accept", offer=1100,
                           template="sounds good to me")
        proc, out = self.gate(
            case_id, draft, approved=True,
            inbound=inbound_msg(offer=1100, text="we can do $1,100",
                                amounts=[1100]),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")
        self.assertEqual(out["rendered"], "sounds good to me")

    def test_accept_offer_must_equal_inbound_offer(self):
        case_id, _ = self.make_case(floor=1200)
        draft = send_draft(action="accept", offer=1100,
                           template="let us close it")
        proc, out = self.gate(
            case_id, draft, approved=True,
            inbound=inbound_msg(offer=1100, text="we can do $1,100"),
        )
        self.assertEqual(proc.returncode, 0, out)
        proc, out = self.gate(
            case_id, send_draft(action="accept", offer=1000,
                                template="let us close it"),
            approved=True,
            inbound=inbound_msg(offer=1100, text="we can do $1,100"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("accept must equal the counterparty's offer",
                      out["reasons"])

    def test_accept_without_inbound_offer_blocks(self):
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(action="accept", offer=1100, template="yes"),
            approved=True,
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("accept requires the counterparty's offer",
                      out["reasons"])

    def test_accept_sign_pay_at_floor_stay_allowed(self):
        # Agreeing actions take a tabled price, so an offer on the
        # floor stays in band: an approved draft passes.
        case_id, _ = self.make_case(floor=1200)
        for action in ("accept", "sign", "pay"):
            with self.subTest(action=action):
                draft = send_draft(action=action, offer=1200,
                                   template="let us proceed")
                kw = {}
                if action == "accept":
                    kw["inbound"] = inbound_msg(offer=1200, text="x")
                proc, out = self.gate(case_id, draft, **kw)
                self.assertEqual(proc.returncode, 3, out)
                self.assertNotIn(
                    "offer is at your limit", out["reasons"]
                )
                proc, out = self.gate(
                    case_id, draft, approved=True, **kw
                )
                self.assertEqual(proc.returncode, 0, out)


if __name__ == "__main__":
    unittest.main()
