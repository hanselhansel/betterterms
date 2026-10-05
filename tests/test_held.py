"""Held drafts and hash-bound approvals (spec 6.3, 6.8): a
needs_approval draft is recorded under held/<sha256>.yaml, an approval
is consumed exactly once, edited text invalidates it, an ambiguous
hash prefix names every match, and held files survive a restart."""

import json
import os
import re
import stat
import threading
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

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
NO_APPROVAL = "no approval recorded for this exact text"


class HeldCase(BtTestCase):
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
        # cancel is irreversible, so the draft always needs approval.
        return send_draft(
            action="cancel", offer=None, template="please end my plan"
        )


class HoldOnNeedsApprovalTest(HeldCase):
    def test_needs_approval_holds_draft(self):
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertRegex(out["hash"], HASH_RE)
        held_dir = case_dir / "held"
        held_file = held_dir / f"{out['hash']}.yaml"
        self.assertTrue(held_file.is_file())
        self.assertEqual(
            stat.S_IMODE(os.stat(held_dir).st_mode), 0o700
        )
        self.assertEqual(
            stat.S_IMODE(os.stat(held_file).st_mode), 0o600
        )
        data = yaml.load(held_file.read_text())
        self.assertEqual(data["hash"], out["hash"])
        self.assertEqual(data["rendered"], out["rendered"])
        self.assertEqual(data["reasons"], out["reasons"])

    def test_clean_pass_holds_nothing(self):
        case_id, case_dir = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(template="a plain question")
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertNotIn("hash", out)
        self.assertFalse((case_dir / "held").exists())

    def test_gate_writes_gate_json(self):
        # The CLI records its own verdict so the mod and widgets read
        # the same answer the agent got; the agent never writes it.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        self.assertEqual(proc.returncode, 3, out)
        saved = json.loads((case_dir / "gate.json").read_text())
        self.assertEqual(saved["result"], "needs_approval")
        self.assertEqual(saved["hash"], out["hash"])
        self.assertEqual(saved["rendered"], out["rendered"])

    def test_gate_writes_gate_json_on_blocked_input(self):
        # A draft refused on the input bounds still records its
        # verdict: gate.json exists on every gate call, blocks and
        # refused inputs included.
        case_id, case_dir = self.make_case()
        big = self.tmp / "big-draft.yaml"
        big.write_text("template: " + "x" * 70000 + "\n")
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(big)
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        saved = json.loads((case_dir / "gate.json").read_text())
        self.assertEqual(saved["result"], "block")
        self.assertEqual(saved["reasons"], out["reasons"])


class ApproveFlowTest(HeldCase):
    def test_approved_requires_matching_approval(self):
        case_id, case_dir = self.make_case()
        draft = self.held_draft()
        proc, out = self.gate(case_id, draft)
        self.assertEqual(proc.returncode, 3, out)
        h = out["hash"]
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertIn(NO_APPROVAL, out["reasons"])
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")
        proc, out = self.gate(case_id, draft, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")

    def test_edited_text_invalidates_approval(self):
        # The user approves the held card, the text changes, and the
        # old approval no longer matches: the send is denied again.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        edited = send_draft(
            action="cancel",
            offer=None,
            template="please end my membership",
        )
        proc, out = self.gate(case_id, edited, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertNotEqual(out["hash"], h)
        self.assertIn(NO_APPROVAL, out["reasons"])

    def test_block_never_consumes_approval(self):
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        run_bt_json(self.home, "held", "approve", case_id, h[:8])
        blocked = send_draft(offer=9000, template="counter")
        proc, out = self.gate(case_id, blocked, approved=True)
        self.assertEqual(proc.returncode, 1, out)
        # The approval file still stands for its own text.
        proc, out = self.gate(
            case_id, self.held_draft(), approved=True
        )
        self.assertEqual(proc.returncode, 0, out)

class TupleBindingTest(HeldCase):
    def test_approval_binds_action_not_just_text(self):
        # The hash covers (action, offer, period, currency, rendered):
        # an approval for a cancel never licenses a send of the same
        # words, and vice versa.
        case_id, case_dir = self.make_case()
        write_case_files(case_dir, brief=dict(BRIEF_PAY, mode="coach"))
        cancel = self.held_draft()
        proc, out = self.gate(case_id, cancel)
        self.assertEqual(proc.returncode, 3, out)
        h = out["hash"]
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        send = send_draft(
            action="send", offer=None, template="please end my plan"
        )
        proc, out = self.gate(case_id, send, approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["rendered"], "please end my plan")
        self.assertNotEqual(out["hash"], h)
        self.assertIn(NO_APPROVAL, out["reasons"])
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, out["hash"][:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        proc, out = self.gate(case_id, send, approved=True)
        self.assertEqual(proc.returncode, 0, out)

    def test_two_sends_cannot_share_one_approval(self):
        # The marker is claimed by an atomic rename: racing consumes
        # split one True and one False, never two sends off one
        # approval. A barrier holds both threads at the claim so the
        # race is forced, not hoped for -- and on filesystems where a
        # plain unlink reports success to both callers, the rename
        # still lets only one through.
        from unittest import mock

        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        draft = self.held_draft()
        barrier = threading.Barrier(2)
        real_rename = os.rename

        def rendezvous(src, dst, *args, **kwargs):
            if str(src).endswith(f"{h}.approved"):
                barrier.wait(timeout=10)
            return real_rename(src, dst, *args, **kwargs)

        results = []
        threads = [
            threading.Thread(
                target=lambda: results.append(
                    held.consume_approval(
                        case_dir, draft, "please end my plan"
                    )
                )
            )
            for _ in range(2)
        ]
        with mock.patch("os.rename", rendezvous):
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(sorted(results), [False, True])
        self.assertFalse(
            (case_dir / "held" / f"{h}.approved").exists()
        )
        self.assertEqual(
            [p.name for p in (case_dir / "held").iterdir()], []
        )


class IntegrityTest(HeldCase):
    def test_held_record_edited_after_hold_is_skipped(self):
        # A held file whose stored fields no longer hash to its name
        # is corrupt: it never lists, and it cannot be approved.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        path = case_dir / "held" / f"{h}.yaml"
        data = yaml.load(path.read_text())
        data["rendered"] = "a different message slipped in"
        path.write_text(yaml.dump(data))
        proc, out = run_bt_json(self.home, "held", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["held"], [])
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("corrupt", out["error"])


class HeldListTest(HeldCase):
    def test_held_survive_restart(self):
        # Held drafts live in files, so a fresh process lists them
        # after a restart.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        self.assertEqual(proc.returncode, 3, out)
        proc, out = run_bt_json(self.home, "held", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(len(out["held"]), 1)
        self.assertEqual(
            out["held"][0]["rendered"], "please end my plan"
        )
        self.assertFalse(out["held"][0]["approved"])

    def test_held_list_empty(self):
        case_id, _ = self.make_case()
        proc, out = run_bt_json(self.home, "held", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["held"], [])

    def test_held_list_skips_a_malformed_record(self):
        # A held file that fails to parse is skipped like a corrupt
        # one: it must not take down the whole listing.
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        self.assertEqual(proc.returncode, 3, out)
        h = out["hash"]
        (case_dir / "held" / f"{'f' * 64}.yaml").write_text(
            "a: 1\na: 2\n"
        )
        proc, out = run_bt_json(self.home, "held", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual([r["hash"] for r in out["held"]], [h])


class ResolveTest(HeldCase):
    def test_hash8_ambiguous_exits_2(self):
        case_id, case_dir = self.make_case()
        held_dir = case_dir / "held"
        held_dir.mkdir()
        h1 = "abcd1234" + "0" * 56
        h2 = "abcd1234" + "1" * 56
        for h in (h1, h2):
            (held_dir / f"{h}.yaml").write_text(
                yaml.dump(
                    {
                        "hash": h,
                        "rendered": f"draft {h[-4:]}",
                        "reasons": [],
                        "held_at": "2026-10-04T00:00:00+00:00",
                    }
                )
            )
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, "abcd1234"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn(h1, out["error"])
        self.assertIn(h2, out["error"])

    def test_hash8_unknown_exits_2(self):
        case_id, _ = self.make_case()
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, "deadbeef"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("no held draft", out["error"])

    def test_full_hash_resolves(self):
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        proc, out = run_bt_json(
            self.home, "held", "approve", case_id, h
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["hash"], h)


class RejectTest(HeldCase):
    def test_held_reject_removes_and_logs(self):
        case_id, case_dir = self.make_case()
        proc, out = self.gate(case_id, self.held_draft())
        h = out["hash"]
        run_bt_json(self.home, "held", "approve", case_id, h[:8])
        proc, out = run_bt_json(
            self.home, "held", "reject", case_id, h[:8]
        )
        self.assertEqual(proc.returncode, 0, out)
        held_dir = case_dir / "held"
        self.assertFalse((held_dir / f"{h}.yaml").exists())
        self.assertFalse((held_dir / f"{h}.approved").exists())
        self.assertIn("rejected", (case_dir / "thread.md").read_text())
        # A rejected draft cannot be sent with --approved either.
        proc, out = self.gate(case_id, self.held_draft(), approved=True)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn(NO_APPROVAL, out["reasons"])


if __name__ == "__main__":
    unittest.main()
