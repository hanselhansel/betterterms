"""Step-2 adversarial findings confirmed against the release branch.

- a ``never_disclose`` item with letters is a hard block wherever it
  appears in the rendered text: a listed term is never a coincidence,
  so it is not a review item
- a ``period`` key present but null on an option or a fact is a
  broken plan: exit 2, never a silent default
- a blocked draft never reports ``offer is at your limit``: on a
  block the reason would leak the floor's equality bit
- the ledger reads a deeply nested line without a recursion crash,
  appends the missing newline a file lacks, and holds a lock across
  the read-dedupe-append sequence so two processes record one case once
"""

import json
import os
import subprocess
import sys
import unittest

from bt_helpers import (
    BtTestCase,
    PriceCase,
    BT,
    new_case,
    plan_for,
    run_bt,
    run_bt_json,
    send_draft,
)


class NeverDiscloseLettersTest(PriceCase):
    def test_never_disclose_with_letters_blocks(self):
        # Items with letters ("CHF 90", "$85/month") match the
        # rendered text literally; a hit is a hard block, not a
        # review item.
        for item, template in (
            ("CHF 90", "the rate is CHF 90 this year"),
            ("$85/month", "you billed $85/month last cycle"),
        ):
            with self.subTest(item=item):
                case_id = self.make_case(
                    brief={"never_disclose": [item]},
                    plan=plan_for("pay", 100, target=80),
                )
                proc, out = self.gate(
                    case_id, send_draft(offer=95, template=template)
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["result"], "block")
                self.assertIn(
                    "never-disclose", " ".join(out["reasons"])
                )
                self.assertIsNone(out["rendered"])


class NullPeriodTest(PriceCase):
    def test_option_period_null_is_input_error(self):
        # options: [{value: 90, period: null}] is a broken plan:
        # exit 2, not a silent default to the plan period.
        case_id = self.make_case(
            plan=dict(
                plan_for("pay", 100, target=80),
                options=[{"label": "a", "value": 90, "period": None}],
            )
        )
        proc, out = self.gate(case_id, send_draft(offer=95, template="hi"))
        self.assertEqual(proc.returncode, 2, out)

    def test_fact_period_null_is_input_error(self):
        # Same for a fact's period key.
        case_id = self.make_case(
            plan=dict(
                plan_for("pay", 100, target=80),
                facts=[{"id": "f1", "text": "they said",
                        "source": "x", "period": None}],
            )
        )
        proc, out = self.gate(case_id, send_draft(offer=95, template="hi"))
        self.assertEqual(proc.returncode, 2, out)


class AtLimitReasonTest(PriceCase):
    def test_block_never_says_at_limit(self):
        # Send offer 60 against floor 60 is the at-limit review hit,
        # but an unknown placeholder blocks the draft: the at-limit
        # reason must be dropped, or the block leaks the floor's
        # equality bit.
        case_id = self.make_case(
            floor=60, plan=plan_for("pay", 60, target=50)
        )
        proc, out = self.gate(
            case_id,
            send_draft(offer=60, template="try {offer} or {nope}"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("unknown placeholder", " ".join(out["reasons"]))
        self.assertNotIn("at your limit", " ".join(out["reasons"]))


class LedgerRobustnessTest(BtTestCase):
    def test_ledger_nested_line_no_recursion(self):
        # A JSON line nested past the interpreter limit is corrupt
        # input: it is skipped with a warning, it never crashes total.
        case_id, _ = new_case(self.home)
        run_bt_json(
            self.home, "ledger", "add", case_id,
            "--before", "80", "--after", "60", "--period", "month",
        )
        ledger = self.home / "ledger.jsonl"
        ledger.write_bytes(ledger.read_bytes() + b'[' * 4000 + b'\n')
        proc, out = run_bt_json(self.home, "ledger", "total")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(out["cases"], 1)
        self.assertGreaterEqual(out["warnings"], 1)

    def test_ledger_append_adds_missing_newline(self):
        # A ledger file whose last line lacks a newline still gets a
        # clean append: the new record lands on its own line.
        self.home.mkdir(parents=True, exist_ok=True)
        seed = {"case_id": "bills-20000101-0000", "saved_per_year": 10,
                "currency": "USD"}
        (self.home / "ledger.jsonl").write_text(json.dumps(seed))
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(
            self.home, "ledger", "add", case_id,
            "--before", "80", "--after", "60", "--period", "month",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc, out = run_bt_json(self.home, "ledger", "total")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["cases"], 2)
        self.assertEqual(out["warnings"], 0)

    def test_ledger_concurrent_adds_count_once(self):
        # Two adds of the same case racing: the read-dedupe-append
        # sequence is locked, so the ledger counts the case once and
        # every loser exits 2 with the duplicate error.
        case_id, _ = new_case(self.home)
        env = dict(os.environ, BETTERTERMS_HOME=str(self.home))
        cmd = [
            sys.executable, str(BT),
            "ledger", "add", case_id,
            "--before", "80", "--after", "60", "--period", "month",
        ]
        procs = [
            subprocess.Popen(
                cmd, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            for _ in range(4)
        ]
        results = [p.communicate() for p in procs]
        codes = [p.returncode for p in procs]
        self.assertEqual(codes.count(0), 1, (codes, results))
        for proc, (stdout, _stderr) in zip(procs, results):
            if proc.returncode == 0:
                continue
            self.assertEqual(proc.returncode, 2, stdout)
            self.assertIn("already recorded", stdout)
        proc, out = run_bt_json(self.home, "ledger", "total")
        self.assertEqual(out["cases"], 1)


if __name__ == "__main__":
    unittest.main()
