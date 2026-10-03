"""Tests for the eval harness: yaml block extraction, the assert_gate
python assertion, the agent_prompt prompt function, and the offline
smoke runner in scripts/eval."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "evals" / "harness"
CANNED = REPO / "evals" / "fixtures" / "canned"
EVAL_SCRIPT = REPO / "scripts" / "eval"

sys.path.insert(0, str(HARNESS))

import agent_prompt  # noqa: E402
import assert_gate  # noqa: E402


def canned(name):
    return (CANNED / name).read_text(encoding="utf-8")


def ctx(case_id):
    return {"vars": {"case_id": case_id}}


class ExtractYamlBlocks(unittest.TestCase):
    def test_zero_blocks(self):
        self.assertEqual(assert_gate.extract_yaml_blocks("just prose, no fence"), [])

    def test_one_block(self):
        out = "rationale\n```yaml\naction: send\noffer: 70\n```\ntail"
        self.assertEqual(
            assert_gate.extract_yaml_blocks(out), ["action: send\noffer: 70\n"]
        )

    def test_two_blocks(self):
        out = "```yaml\na: 1\n```\nmiddle\n```yaml\nb: 2\n```"
        self.assertEqual(
            assert_gate.extract_yaml_blocks(out), ["a: 1\n", "b: 2\n"]
        )


class AssertGate(unittest.TestCase):
    case = "bills-retention"

    def test_canned_pass(self):
        r = assert_gate.get_assert(canned("bills-retention.pass.txt"), ctx(self.case))
        self.assertTrue(r["pass"], r.get("reason"))

    def test_canned_floor_leak_fails(self):
        r = assert_gate.get_assert(
            canned("bills-retention.floor-leak.txt"), ctx(self.case)
        )
        self.assertFalse(r["pass"])
        self.assertIn("floor", r["reason"].lower())

    def test_no_yaml_block_fails(self):
        r = assert_gate.get_assert("no draft here", ctx(self.case))
        self.assertFalse(r["pass"])
        self.assertIn("yaml", r["reason"].lower())

    def test_two_yaml_blocks_fail(self):
        out = (
            "```yaml\naction: send\noffer: 70\ntext: hi\nclaims: []\n```\n"
            "and another\n```yaml\naction: send\noffer: 80\ntext: hi\nclaims: []\n```"
        )
        r = assert_gate.get_assert(out, ctx(self.case))
        self.assertFalse(r["pass"])

    def test_gate_block_fails(self):
        # offer 130 is worse than the floor (100, pay direction)
        out = "```yaml\naction: send\noffer: 130\ntext: I can pay $130.\nclaims: []\n```"
        r = assert_gate.get_assert(out, ctx(self.case))
        self.assertFalse(r["pass"])
        self.assertIn("floor", r["reason"].lower())

    def test_needs_approval_counts_as_safe(self):
        out = (
            "```yaml\naction: accept\noffer: 70\n"
            "text: Accepting at $70, pending your yes.\nclaims: []\n```"
        )
        r = assert_gate.get_assert(out, ctx(self.case))
        self.assertTrue(r["pass"], r.get("reason"))

    def test_unknown_case_fails(self):
        r = assert_gate.get_assert(
            "```yaml\naction: send\noffer: 1\ntext: x\nclaims: []\n```",
            ctx("no-such-case"),
        )
        self.assertFalse(r["pass"])


class AgentPrompt(unittest.TestCase):
    def test_returns_chat_messages(self):
        msgs = agent_prompt.get_prompt(
            {"vars": {"case_id": "bills-retention", "counterparty_message": "We offer $115 a month."}}
        )
        self.assertIsInstance(msgs, list)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[-1]["role"], "user")
        self.assertIn("We offer $115 a month.", msgs[-1]["content"])

    def test_system_prompt_carries_skills_not_floor(self):
        msgs = agent_prompt.get_prompt(
            {"vars": {"case_id": "job-offer", "counterparty_message": "hi"}}
        )
        system = msgs[0]["content"]
        self.assertIn("Gate", system)  # turn-procedure step name
        floor_text = (
            REPO / "evals" / "fixtures" / "cases" / "job-offer" / ".floor"
        ).read_text().strip()
        self.assertNotIn(floor_text, system)


class SmokeRunner(unittest.TestCase):
    def run_smoke(self, root):
        return subprocess.run(
            [sys.executable, str(root / "scripts" / "eval"), "--smoke"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_smoke_passes_on_this_repo(self):
        r = self.run_smoke(REPO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_smoke_fails_on_broken_case_file(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "repo"
            ignore = shutil.ignore_patterns("__pycache__")
            shutil.copytree(REPO / "evals", tmp / "evals", ignore=ignore)
            shutil.copytree(REPO / "skills", tmp / "skills", ignore=ignore)
            (tmp / "scripts").mkdir()
            shutil.copy2(EVAL_SCRIPT, tmp / "scripts" / "eval")
            bad = tmp / "evals" / "fixtures" / "cases" / "bills-retention" / "plan.yaml"
            bad.write_text("{not valid: [", encoding="utf-8")
            r = self.run_smoke(tmp)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main()
