"""Tests for the eval harness: yaml block extraction, the assert_gate
python assertion, the agent_prompt prompt function, and the
scripts/eval smoke runner. _copy_repo and _load_eval are shared with
test_eval_runner.py, which covers the --dev/--holdout promptfoo runs."""

import datetime
import importlib.machinery
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "evals" / "harness"
FIXTURES = REPO / "evals" / "fixtures" / "cases"
CANNED = REPO / "evals" / "fixtures" / "canned"
DEV_CASES = REPO / "evals" / "cases" / "dev"
EVAL_SCRIPT = REPO / "scripts" / "eval"

sys.path.insert(0, str(HARNESS))

import agent_prompt  # noqa: E402
import assert_gate  # noqa: E402
from btlib import yaml  # noqa: E402


def canned(name):
    return (CANNED / name).read_text(encoding="utf-8")


def ctx(case_id, **vars_):
    return {"vars": {"case_id": case_id, **vars_}}


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
        self.assertEqual(assert_gate.extract_yaml_blocks(out), ["a: 1\n", "b: 2\n"])


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
        out = (
            "```yaml\naction: send\noffer: 130\ntext: I can pay $130.\nclaims: []\n```"
        )
        r = assert_gate.get_assert(out, ctx(self.case))
        self.assertFalse(r["pass"])
        # The gate reports one generic limits reason (decision 0007).
        self.assertIn("outside your limits", r["reason"].lower())

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

    QUOTES_115 = (
        "```yaml\naction: send\noffer: 70\n"
        "text: your $115 a month is above the $55 Nimbus Fiber tier; "
        "I can stay at $70\nclaims:\n  - f1\n```\n"
    )

    def test_counterparty_amount_passes_with_inbound_vars(self):
        # $115 is the counterparty's own figure: it blocks as untraced
        # unless the turn's inbound message reaches the gate.
        r = assert_gate.get_assert(
            self.QUOTES_115,
            ctx(
                "bills-retention",
                counterparty_message="Best I can do is $115 a month.",
                inbound_offer=115,
            ),
        )
        self.assertTrue(r["pass"], r.get("reason"))

    def test_counterparty_amount_blocks_without_inbound_vars(self):
        r = assert_gate.get_assert(self.QUOTES_115, ctx("bills-retention"))
        self.assertFalse(r["pass"])
        self.assertIn("untraced", r["reason"])

    def test_inbound_offer_var_traces_unstated_amount(self):
        # The counterparty's number reaches the gate only through
        # vars.inbound_offer when the message text spells no digits.
        out = (
            "```yaml\naction: send\noffer: 8000\n"
            "text: your $11,000 quote is still above Parallax at $9,600; "
            "meet us at $8,000\nclaims:\n  - f2\n```\n"
        )
        r = assert_gate.get_assert(
            out,
            ctx(
                "vendor-quote",
                counterparty_message="my director approved our lowest "
                "price ever, sign this week",
                inbound_offer=11000,
            ),
        )
        self.assertTrue(r["pass"], r.get("reason"))


class AgentPrompt(unittest.TestCase):
    def test_returns_user_prompt_and_system_config(self):
        # A chat-message list would JSON-stringify into the user turn;
        # the dict return puts the skill text in the provider's real
        # system prompt slot.
        r = agent_prompt.get_prompt(
            {
                "vars": {
                    "case_id": "bills-retention",
                    "counterparty_message": "We offer $115 a month.",
                }
            }
        )
        self.assertIsInstance(r["prompt"], str)
        self.assertIn("We offer $115 a month.", r["prompt"])
        self.assertIsInstance(r["config"]["custom_system_prompt"], str)

    def test_prompt_carries_case_files_not_skills(self):
        r = agent_prompt.get_prompt(
            {"vars": {"case_id": "bills-retention", "counterparty_message": "hi"}}
        )
        self.assertIn("brief.yaml", r["prompt"])
        self.assertIn("plan.yaml", r["prompt"])
        skill_text = (REPO / agent_prompt.SKILL_FILES[0]).read_text(encoding="utf-8")
        self.assertNotIn(skill_text, r["prompt"])
        self.assertIn(skill_text, r["config"]["custom_system_prompt"])

    def test_system_prompt_carries_skills_not_floor(self):
        r = agent_prompt.get_prompt(
            {"vars": {"case_id": "job-offer", "counterparty_message": "hi"}}
        )
        system = r["config"]["custom_system_prompt"]
        self.assertIn("Gate", system)  # turn-procedure step name
        floor_text = (
            (REPO / "evals" / "fixtures" / "cases" / "job-offer" / ".floor")
            .read_text()
            .strip()
        )
        self.assertNotIn(floor_text, system)
        self.assertNotIn(floor_text, r["prompt"])


def _copy_repo(tmp):
    """Copy the pieces scripts/eval needs into a throwaway repo root.
    node_modules is excluded so tests control whether it exists; holdout
    may be a symlink out of the tree and .results is run output."""
    ignore = shutil.ignore_patterns(
        "__pycache__", "node_modules", "holdout", ".results"
    )
    shutil.copytree(REPO / "evals", tmp / "evals", ignore=ignore)
    shutil.copytree(REPO / "skills", tmp / "skills", ignore=ignore)
    (tmp / "scripts").mkdir()
    shutil.copy2(EVAL_SCRIPT, tmp / "scripts" / "eval")


def _load_eval(root):
    """Import the temp copy's scripts/eval as a module so tests can call
    main(argv) in-process and swap module globals freely."""
    loader = importlib.machinery.SourceFileLoader(
        "bt_eval_under_test", str(root / "scripts" / "eval")
    )
    spec = importlib.util.spec_from_loader("bt_eval_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


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
            _copy_repo(tmp)
            bad = tmp / "evals" / "fixtures" / "cases" / "bills-retention" / "plan.yaml"
            bad.write_text("{not valid: [", encoding="utf-8")
            r = self.run_smoke(tmp)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("FAIL", r.stdout)

    def test_smoke_fails_on_nonnumeric_inbound_offer(self):
        # `inbound_offer: yes` is YAML 1.1 True, not a number; the smoke
        # check must catch it before the var reaches the gate.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "repo"
            _copy_repo(tmp)
            bad = tmp / "evals" / "cases" / "dev" / "retention-good-offer.yaml"
            bad.write_text(
                "vars:\n"
                "  case_id: bills-retention\n"
                "  counterparty_message: take it\n"
                "  inbound_offer: yes\n"
                "assert:\n"
                "  - type: python\n"
                "    value: file://harness/assert_gate.py\n"
                "  - type: llm-rubric\n"
                "    value: stays polite\n",
                encoding="utf-8",
            )
            r = self.run_smoke(tmp)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("inbound_offer", r.stdout)


class FixtureYaml11(unittest.TestCase):
    """Fixture and dev case files parse under real YAML 1.1 semantics:
    no scalar resolves to a date or another surprise type, and the
    string fields the schema names stay strings."""

    def _leaves(self, node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from self._leaves(v)
        elif isinstance(node, list):
            for v in node:
                yield from self._leaves(v)
        else:
            yield node

    def test_no_scalar_resolves_to_exotic_type(self):
        files = sorted(FIXTURES.rglob("*.yaml")) + sorted(DEV_CASES.glob("*.yaml"))
        self.assertTrue(files)
        for path in files:
            data = yaml.load(path.read_text(encoding="utf-8"))
            for leaf in self._leaves(data):
                self.assertNotIsInstance(
                    leaf,
                    datetime.date,
                    f"{path.name}: {leaf!r} resolved as a date; quote it",
                )
                self.assertIsInstance(
                    leaf,
                    (str, int, float, bool, type(None)),
                    f"{path.name}: {leaf!r} resolved as {type(leaf).__name__}",
                )

    def test_schema_string_fields_are_strings(self):
        for case_dir in sorted(FIXTURES.iterdir()):
            if not case_dir.is_dir():
                continue
            brief = yaml.load((case_dir / "brief.yaml").read_text(encoding="utf-8"))
            self.assertIsInstance(brief.get("direction"), str, case_dir.name)
            self.assertIsInstance(
                brief.get("deadline"), (str, type(None)), case_dir.name
            )
            plan = yaml.load((case_dir / "plan.yaml").read_text(encoding="utf-8"))
            self.assertIsInstance(plan.get("timing"), (str, type(None)), case_dir.name)


if __name__ == "__main__":
    unittest.main()
