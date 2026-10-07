"""The current-hash check in ``bt.py held approve`` (spec 6.3, 6.8).
gate.json names the draft the last gate verdict held; approve marks
only that hash. A stale card, a case with no recorded verdict, and a
verdict of any other kind all refuse with exit 2 and a plain reason.
Split from test_held.py under the 400-line cap."""

import unittest

from bt_helpers import run_bt_json, send_draft
from btlib import held
from test_held import HeldCase

STALE = "not the current held draft"


class CurrentHashTest(HeldCase):
    def test_approve_refuses_a_stale_hash(self):
        # gate.json names the draft the last gate verdict held. A held
        # record whose hash differs (a card written beside it, a draft
        # from before a pass or block verdict) cannot be approved:
        # exit 2 with a plain reason, no marker.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        current = out["hash"]
        # A second record written beside the current one resolves but
        # is not the hash the verdict names. The gate drops the
        # previous current itself when it holds a new hash, so a
        # stale record only ever sits beside a verdict it did not
        # come from.
        other = send_draft(
            action="cancel",
            offer=None,
            template="please end my membership",
        )
        stale = held.hold(
            case_dir, other, "please end my membership", []
        )
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
        # A block verdict retires the earlier held record outright,
        # so the old hash cannot be approved and the draft would
        # have to be held and approved again.
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
        self.assertIn("no held draft", out["error"])
        self.assertFalse((case_dir / "held" / f"{h}.yaml").exists())

    def test_a_new_hold_drops_the_previous_current_record(self):
        # Holding a new hash for a case drops the old current record
        # quietly, like `held drop`: no `## rejected` thread marker,
        # and one card stays current in the pane.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        self.assertEqual(proc.returncode, 3, out)
        stale = out["hash"]
        newer = send_draft(
            action="cancel",
            offer=None,
            template="please end my membership",
        )
        proc, out = self.gate(case_id, newer)
        self.assertEqual(proc.returncode, 3, out)
        current = out["hash"]
        self.assertNotEqual(stale, current)
        held_dir = case_dir / "held"
        self.assertFalse((held_dir / f"{stale}.yaml").exists())
        self.assertTrue((held_dir / f"{current}.yaml").is_file())
        # The drop is quiet: no reject marker lands in thread.md.
        thread = case_dir / "thread.md"
        text = thread.read_text() if thread.exists() else ""
        self.assertNotIn("rejected", text)
        # held list reports exactly one record.
        proc, out = run_bt_json(self.home, "held", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            [e["hash"] for e in out["held"]], [current]
        )

    def test_re_hold_of_the_same_tuple_keeps_the_record(self):
        # Re-gating identical text holds the same hash: the record
        # must not be dropped by its own refresh.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        proc, out = self.gate(case_id, self.held_draft())
        self.assertEqual(out["hash"], h)
        self.assertTrue(
            (case_dir / "held" / f"{h}.yaml").is_file()
        )


if __name__ == "__main__":
    unittest.main()
