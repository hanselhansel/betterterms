"""The current-hash check in ``bt.py held approve`` (spec 6.3, 6.8).
gate.json names the draft the last gate verdict held; approve marks
only that hash. A stale card, a case with no recorded verdict, and a
verdict of any other kind all refuse with exit 2 and a plain reason.
Split from test_held.py under the 400-line cap."""

import unittest

from bt_helpers import run_bt_json, send_draft
from test_held import HeldCase

STALE = "not the current held draft"


class CurrentHashTest(HeldCase):
    def test_approve_refuses_a_stale_hash(self):
        # gate.json names the draft the last gate verdict held. A held
        # record whose hash differs (an old card, a draft edited since)
        # cannot be approved: exit 2 with a plain reason, no marker.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        stale = out["hash"]
        newer = send_draft(
            action="cancel",
            offer=None,
            template="please end my membership",
        )
        proc, out = self.gate(case_id, newer)
        current = out["hash"]
        self.assertNotEqual(stale, current)
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, stale[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn(STALE, out["error"])
        self.assertFalse(
            (case_dir / "held" / f"{stale}.approved").exists()
        )
        # The hash the verdict names still approves.
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, current[:8]
        )
        self.assertEqual(proc.returncode, 0, out)

    def test_approve_refuses_without_gate_json(self):
        # A held record with no recorded verdict at all refuses too:
        # missing gate.json is never proof the draft is current.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        (case_dir / "gate.json").unlink()
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn(STALE, out["error"])
        self.assertFalse(
            (case_dir / "held" / f"{h}.approved").exists()
        )

    def test_approve_refuses_after_a_block_verdict(self):
        # A block verdict rewrites gate.json without a hash, so a held
        # draft from before the block is no longer current.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        blocked = send_draft(offer=9000, template="counter")
        proc, out = self.gate(case_id, blocked)
        self.assertEqual(proc.returncode, 1, out)
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn(STALE, out["error"])


if __name__ == "__main__":
    unittest.main()
