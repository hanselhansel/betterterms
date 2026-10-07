"""Held-record, marker and verdict integrity (spec 6.3).

A held record authorizes only when its stored tuple -- every field
present with its written type -- hashes back to its filename, its
approval marker names that hash, and the marker is still the one
the current ``needs_approval`` verdict held. ``supersede`` retires
markers independently of record validity, so an orphan or a marker
paired with a corrupt record can never resurrect onto a later
same-hash record.
"""

import json
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
from btlib import held, yaml

NO_APPROVAL = "no approval recorded for this exact text"


class SecurityCase(BtTestCase):
    def make_case(self):
        case_id, case_dir = new_case(self.home)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY),
            plan=plan_for("pay", 1200),
            floor=1200,
        )
        return case_id, case_dir

    def gate(self, case_id, draft, approved=False):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if approved:
            args.append("--approved")
        return run_bt_json(self.home, *args)

    def held_draft(self):
        return send_draft(
            action="cancel", offer=None, template="please end my plan"
        )

    def hold_approved(self, case_id, draft):
        """Gate once to hold, approve the printed hash, return it."""
        _proc, out = self.gate(case_id, draft)
        h = out["hash"]
        proc, _ = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0)
        return h

    def record(self, case_dir, h):
        return yaml.load(
            (case_dir / "held" / f"{h}.yaml").read_text()
        )

    def rewrite(self, case_dir, h, data):
        (case_dir / "held" / f"{h}.yaml").write_text(yaml.dump(data))


class RecordStrictnessTest(SecurityCase):
    def test_retyped_offer_is_corrupt(self):
        # offer written back as a string lookalike can never stand in
        # for the numeric tuple the owner reviewed.
        case_id, case_dir = self.make_case()
        draft = send_draft(
            action="pay", offer=1100, template="paying the bill"
        )
        _proc, out = self.gate(case_id, draft)
        h = out["hash"]
        data = self.record(case_dir, h)
        data["offer"] = "1100.00"
        self.rewrite(case_dir, h, data)
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("corrupt", out["error"])

    def test_missing_inbound_field_is_corrupt(self):
        case_id, case_dir = self.make_case()
        _proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        data = self.record(case_dir, h)
        del data["inbound"]
        self.rewrite(case_dir, h, data)
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("corrupt", out["error"])

    def test_nonfinite_offer_is_corrupt(self):
        # A stored .nan/.inf collapses to the null-offer hash under
        # cases.num: it must be rejected before the hash is compared.
        case_id, case_dir = self.make_case()
        _proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        for bad in (".nan", ".inf"):
            path = case_dir / "held" / f"{h}.yaml"
            text = path.read_text().replace(
                "offer: null", f"offer: {bad}"
            )
            path.write_text(text)
            proc, out = run_bt_json(
                self.home, "held", "approve", case_id, h[:8]
            )
            self.assertEqual(proc.returncode, 2, out)
            self.assertIn("corrupt", out["error"])

    def test_nonpositive_offer_is_corrupt(self):
        case_id, case_dir = self.make_case()
        _proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        path = case_dir / "held" / f"{h}.yaml"
        path.write_text(
            path.read_text().replace("offer: null", "offer: -5")
        )
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("corrupt", out["error"])


class VerdictStrictnessTest(SecurityCase):
    def test_pass_verdict_with_a_hash_is_not_current(self):
        # gate.json naming a pass verdict must never authorize: the
        # current-hash check requires a needs_approval verdict.
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        h = self.hold_approved(case_id, draft)
        (case_dir / "gate.json").write_text(
            json.dumps({"result": "pass", "hash": h, "reasons": []})
        )
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(NO_APPROVAL, out["reasons"])

    def test_block_verdict_with_a_hash_is_not_current(self):
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        h = self.hold_approved(case_id, draft)
        (case_dir / "gate.json").write_text(
            json.dumps({"result": "block", "hash": h, "reasons": []})
        )
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)

    def test_malformed_hash_in_verdict_is_not_current(self):
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        h = self.hold_approved(case_id, draft)
        (case_dir / "gate.json").write_text(
            json.dumps(
                {"result": "needs_approval", "hash": 12345,
                 "reasons": []}
            )
        )
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(NO_APPROVAL, out["reasons"])


class MarkerStrictnessTest(SecurityCase):
    def test_claimed_marker_contents_are_validated(self):
        # A marker is claimed by rename and validated after the
        # claim: contents naming another hash never authorize, and
        # the claimed file is removed.
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        proc, out = self.gate(case_id, draft)
        h = out["hash"]
        (case_dir / "held" / f"{h}.approved").write_text(
            yaml.dump({"hash": "0" * 64, "approved_at": "t"})
        )
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertFalse(
            (case_dir / "held" / f"{h}.approved").exists()
        )
        self.assertFalse(
            [
                p
                for p in (case_dir / "held").iterdir()
                if p.name.endswith(".claimed")
            ]
        )

    def test_orphan_marker_cannot_resurrect(self):
        # A marker with no record behind it retires on the next
        # supersede; a later same-hash re-hold must not resurrect it.
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        proc, out = self.gate(case_id, draft)
        h = out["hash"]
        d = case_dir / "held"
        (d / f"{h}.yaml").unlink()
        (d / f"{h}.approved").write_text(
            yaml.dump({"hash": h, "approved_at": "t"})
        )
        held.supersede(case_dir, None)
        self.assertFalse((d / f"{h}.approved").exists())
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(NO_APPROVAL, out["reasons"])

    def test_marker_on_a_corrupt_record_retires(self):
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        proc, out = self.gate(case_id, draft)
        h = out["hash"]
        d = case_dir / "held"
        (d / f"{h}.yaml").write_text("a: 1\na: 2\n")
        (d / f"{h}.approved").write_text(
            yaml.dump({"hash": h, "approved_at": "t"})
        )
        held.supersede(case_dir, None)
        self.assertFalse((d / f"{h}.approved").exists())
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)

    def test_supersede_keeps_the_current_marker(self):
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        h = self.hold_approved(case_id, draft)
        held.supersede(case_dir, h)
        self.assertTrue(
            (case_dir / "held" / f"{h}.approved").exists()
        )


if __name__ == "__main__":
    unittest.main()
