"""``bt.py held disarm``: the marker-only counterpart of approve and
reject (spec 6.3). The mod runs it when a re-armed ``.approved``
marker was not spent by the re-gate, so a leftover marker never waits
on disk for a later call. Split from test_held.py under the 400-line
cap."""

import unittest

from bt_helpers import run_bt_json
from test_held import HeldCase


class DisarmTest(HeldCase):
    def test_disarm_drops_only_the_marker(self):
        # held disarm clears the approval marker but keeps the held
        # draft: the mod runs it when a re-armed marker was not spent
        # by the re-gate, so a leftover marker never outlives its press.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        run_bt_json(self.home, "held", "approve", case_id, h[:8])
        held_dir = case_dir / "held"
        marker = held_dir / f"{h}.approved"
        self.assertTrue(marker.is_file())
        proc, out = run_bt_json(
            self.home, "held", "disarm", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["hash"], h)
        self.assertFalse(marker.exists())
        self.assertTrue((held_dir / f"{h}.yaml").is_file())
        # The draft still lists, unapproved, and cannot send.
        proc, out = run_bt_json(self.home, "held", "list", case_id)
        self.assertEqual(len(out["held"]), 1)
        self.assertFalse(out["held"][0]["approved"])
        proc, out = self.gate(
            case_id, self.held_draft(), approved=True
        )
        self.assertEqual(proc.returncode, 3, out)

    def test_disarm_without_marker_is_a_noop(self):
        # A hash that resolves to a held draft with no marker clears
        # quietly; the mod only ever disarms just-armed markers.
        case_id, _ = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        proc, out = run_bt_json(
            self.home, "held", "disarm", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["hash"], h)

    def test_disarm_clears_a_stale_marker(self):
        # A marker whose record is already gone still disarms: the
        # resolve matches marker names, not only live records.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        held_dir = case_dir / "held"
        (held_dir / f"{h}.yaml").unlink()
        marker = held_dir / f"{h}.approved"
        marker.write_text(f"hash: {h}\n")
        proc, out = run_bt_json(
            self.home, "held", "disarm", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertFalse(marker.exists())

    def test_disarm_unknown_hash_exits_2(self):
        case_id, _ = self.make_case()
        proc, out = run_bt_json(
            self.home, "held", "disarm", case_id, "deadbeef"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("no held draft", out["error"])


if __name__ == "__main__":
    unittest.main()
