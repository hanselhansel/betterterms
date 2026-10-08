"""``bt.py held drop``: the quiet remove. The mod's Edit flow drops
the held record for the old text before re-gating the edited draft.
Unlike reject, drop is bookkeeping: no ``## rejected`` line lands in
thread.md. The prefix resolves exactly like reject: unknown or
ambiguous answers exit 2.
"""

import unittest

from bt_helpers import run_bt_json
from test_held import HeldCase, NO_APPROVAL


class DropTest(HeldCase):
    def test_held_drop_removes_without_thread_marker(self):
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        run_bt_json(self.home, "held", "approve", case_id, h[:8])
        thread_before = (
            (case_dir / "thread.md").read_text()
            if (case_dir / "thread.md").exists() else ""
        )
        proc, out = run_bt_json(
            self.home, "held", "drop", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        held_dir = case_dir / "held"
        self.assertFalse((held_dir / f"{h}.yaml").exists())
        self.assertFalse((held_dir / f"{h}.approved").exists())
        thread_after = (
            (case_dir / "thread.md").read_text()
            if (case_dir / "thread.md").exists() else ""
        )
        self.assertEqual(thread_after, thread_before)
        # A dropped draft cannot be sent with --approved either.
        proc, out = self.gate(case_id, self.held_draft(), approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(NO_APPROVAL, out["reasons"])

    def test_held_drop_uses_reject_refusal_rules(self):
        case_id, _ = self.make_case()
        proc, out = run_bt_json(
            self.home, "held", "drop", case_id, "deadbeef"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("no held draft", out["error"])
        proc, out = run_bt_json(
            self.home, "held", "drop", case_id, "nothex"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("hash prefix", out["error"])


if __name__ == "__main__":
    unittest.main()
