"""Legacy held records (spec 6.3): drafts held by builds before
approvals bound the send tuple carry a filename that is the SHA-256
of the rendered text alone. They still list -- flagged ``legacy``
with a re-run-the-gate note so the mod skips them -- but they can
never be approved or spent. Split from test_held.py under the
400-line cap."""

import unittest

from bt_helpers import run_bt_json
from btlib import yaml
from test_held import HeldCase


class LegacyRecordTest(HeldCase):
    """Records written before approvals bound the send tuple are
    hashed on the rendered text alone. They still list -- flagged
    ``legacy`` so the mod skips them -- but they can never be
    approved or spent: the answer is to re-run the gate."""

    LEGACY = "held by an older version; re-run the gate"

    def plant_legacy(self, case_dir, rendered="please end my plan"):
        import hashlib

        h = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        d = case_dir / "held"
        d.mkdir(exist_ok=True)
        (d / f"{h}.yaml").write_text(
            yaml.dump(
                {
                    "hash": h,
                    "rendered": rendered,
                    "reasons": ["cancel needs your yes"],
                    "held_at": "2026-10-04T00:00:00+00:00",
                }
            )
        )
        return h

    def test_legacy_record_lists_flagged(self):
        case_id, case_dir = self.make_case()
        h = self.plant_legacy(case_dir)
        proc, out = run_bt_json(self.home, "held", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(len(out["held"]), 1)
        rec = out["held"][0]
        self.assertEqual(rec["hash"], h)
        self.assertTrue(rec["legacy"])
        self.assertEqual(rec["note"], self.LEGACY)

    def test_legacy_record_cannot_be_approved(self):
        case_id, case_dir = self.make_case()
        h = self.plant_legacy(case_dir)
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn(self.LEGACY, out["error"])
        self.assertFalse((case_dir / "held" / f"{h}.approved").exists())

    def test_legacy_marker_never_satisfies_the_gate(self):
        # Even with a forged .approved marker, a legacy hash never
        # matches the tuple the gate now binds.
        case_id, case_dir = self.make_case()
        h = self.plant_legacy(case_dir)
        (case_dir / "held" / f"{h}.approved").write_text("x\n")
        proc, out = self.gate(
            case_id, self.held_draft(), approved=True
        )
        self.assertEqual(proc.returncode, 3, out)

    def test_legacy_record_can_still_be_dropped(self):
        case_id, case_dir = self.make_case()
        h = self.plant_legacy(case_dir)
        proc, out = run_bt_json(
            self.home, "held", "reject", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertFalse((case_dir / "held" / f"{h}.yaml").exists())


if __name__ == "__main__":
    unittest.main()
