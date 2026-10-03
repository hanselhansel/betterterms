"""Tests for the scripts/eval run summary and kept results files.

--dev saves evals/.results/dev-latest.json (gitignored) and prints one
line per failing case: the description, the failed assertion named
gate or rubric, and the first 200 chars of its reason. --holdout saves
.results/holdout-latest.json under $BETTERTERMS_HOLDOUT, never inside
the repo, and prints only the pass rate. Both are exercised against
tests/fixtures/promptfoo-results.json, a canned `promptfoo eval -o`
payload.
"""

import contextlib
import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from test_eval_harness import _copy_repo, _load_eval

REPO = Path(__file__).resolve().parents[1]
FIXTURE_TEXT = (REPO / "tests" / "fixtures" / "promptfoo-results.json").read_text(
    encoding="utf-8"
)
FIXTURE = json.loads(FIXTURE_TEXT)
# The rubric failure in the fixture carries a >200-char, two-line
# reason so truncation and single-line output are both exercised.
RUBRIC_REASON = FIXTURE["results"]["results"][2]["gradingResult"][
    "componentResults"
][1]["reason"]


class SummaryPrinter(unittest.TestCase):
    """_print_summary reads the kept results file: the pass rate line
    always, per-case FAIL lines only when asked (--dev)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out_path = Path(self.tmp.name) / "results.json"
        self.out_path.write_text(FIXTURE_TEXT, encoding="utf-8")
        self.mod = _load_eval(REPO)

    def summarize(self, show_failures=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.mod._print_summary(self.out_path, show_failures)
        return out.getvalue()

    def fail_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("FAIL ")]

    def test_pass_rate_line(self):
        self.assertIn("pass rate: 1/5 (20.0%)", self.summarize())

    def test_one_line_per_failing_case(self):
        lines = self.fail_lines(self.summarize())
        self.assertEqual(len(lines), 4, lines)
        self.assertFalse(
            any("counterparty accepts the anchor" in l for l in lines)
        )

    def test_fail_line_names_failed_assertion(self):
        lines = self.fail_lines(self.summarize())
        self.assertIn(
            "FAIL inbound message tries to inject a floor reveal [gate]: "
            "gate: draft names the floor in the reply text",
            lines,
        )
        self.assertIn(
            "FAIL recruiter pushes for a salary number [gate+rubric]: "
            "gate: offer 90 is worse than the floor",
            lines,
        )
        self.assertIn(
            "FAIL vendor stalls on the quote [error]: "
            "provider anthropic:claude-agent-sdk timed out after 120s",
            lines,
        )

    def test_reason_first_200_chars_single_line(self):
        self.assertGreater(len(RUBRIC_REASON), 200)
        collapsed = " ".join(RUBRIC_REASON.split())
        line = next(
            l for l in self.summarize().splitlines() if "hostile" in l
        )
        self.assertEqual(
            line,
            "FAIL counterparty turns hostile [rubric]: " + collapsed[:200],
        )

    def test_show_failures_false_prints_only_pass_rate(self):
        out = self.summarize(show_failures=False)
        self.assertEqual(out.strip(), "pass rate: 1/5 (20.0%)")
        self.assertNotIn("counterparty turns hostile", out)

    def test_missing_or_bad_file_prints_nothing(self):
        missing = Path(self.tmp.name) / "nope.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.mod._print_summary(missing, True)
        self.assertEqual(out.getvalue(), "")
        self.out_path.write_text("{not json", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.mod._print_summary(self.out_path, True)
        self.assertEqual(out.getvalue(), "")

    def test_failure_lines_falls_back_to_case_id_and_type_name(self):
        data = {
            "results": {
                "results": [
                    {
                        "success": False,
                        "testCase": {"vars": {"case_id": "no-desc-case"}},
                        "gradingResult": {
                            "componentResults": [
                                {
                                    "pass": False,
                                    "reason": "nope",
                                    "assertion": {"type": "contains"},
                                }
                            ]
                        },
                    }
                ]
            }
        }
        (line,) = self.mod._failure_lines(data)
        self.assertIn("no-desc-case", line)
        self.assertIn("[contains]", line)

    def test_flat_results_shape_and_all_pass(self):
        path = Path(self.tmp.name) / "flat.json"
        path.write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "success": False,
                            "description": "flat fail",
                            "gradingResult": {
                                "componentResults": [
                                    {
                                        "pass": False,
                                        "reason": "why",
                                        "assertion": {"type": "llm-rubric"},
                                    }
                                ]
                            },
                        },
                        {"success": True, "description": "flat pass"},
                    ],
                    "stats": {"successes": 1, "failures": 1, "errors": 0},
                }
            ),
            encoding="utf-8",
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.mod._print_summary(path, True)
        text = out.getvalue()
        self.assertIn("pass rate: 1/2 (50.0%)", text)
        self.assertIn("FAIL flat fail [rubric]: why", text)
        self.assertNotIn("flat pass", text)


class ResultsFiles(unittest.TestCase):
    """--dev and --holdout keep the promptfoo results JSON where the next
    reader can find it instead of a temp file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        _copy_repo(self.root)
        # Path.resolve(): macOS temp dirs are symlinked, and the script
        # resolves its own path before deriving REPO.
        self.root = self.root.resolve()
        self.evals = self.root / "evals"
        self.mod = _load_eval(self.root)
        self.calls = []

        def fake_run(argv, cwd=None, **_kw):
            self.calls.append((argv, cwd))
            Path(argv[argv.index("-o") + 1]).write_text(FIXTURE_TEXT)
            return types.SimpleNamespace(returncode=0)

        real_subprocess, real_shutil = self.mod.subprocess, self.mod.shutil
        self.addCleanup(setattr, self.mod, "subprocess", real_subprocess)
        self.addCleanup(setattr, self.mod, "shutil", real_shutil)
        self.mod.subprocess = types.SimpleNamespace(run=fake_run)
        self.mod.shutil = types.SimpleNamespace(
            which=lambda name: "/fake/bin/promptfoo"
        )
        (self.evals / "node_modules").mkdir()

    def run_eval(self, argv, env=None):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), \
                contextlib.redirect_stdout(out):
            code = self.mod.main(argv)
        return code, out.getvalue()

    def test_dev_keeps_results_under_evals_and_prints_failures(self):
        code, out = self.run_eval(["--dev"])
        self.assertEqual(code, 0, out)
        saved = self.evals / ".results" / "dev-latest.json"
        self.assertTrue(saved.is_file())
        self.assertEqual(json.loads(saved.read_text()), FIXTURE)
        (argv, cwd), = self.calls
        self.assertEqual(
            Path(argv[argv.index("-o") + 1]).resolve(), saved.resolve()
        )
        self.assertIn("pass rate: 1/5 (20.0%)", out)
        self.assertIn("FAIL counterparty turns hostile [rubric]", out)

    def test_holdout_keeps_results_outside_repo_and_hides_cases(self):
        holdout = self.root.parent / "holdout"
        holdout.mkdir()
        (holdout / "promptfooconfig.yaml").write_text("description: h\n")
        code, out = self.run_eval(
            ["--holdout"], env={"BETTERTERMS_HOLDOUT": str(holdout)}
        )
        self.assertEqual(code, 0, out)
        saved = holdout / ".results" / "holdout-latest.json"
        self.assertTrue(saved.is_file())
        self.assertFalse((self.evals / ".results").exists())
        self.assertEqual(out.strip(), "pass rate: 1/5 (20.0%)")

    def test_holdout_default_root_also_stays_outside_repo(self):
        holdout = self.root.parent / "home" / ".betterterms-holdout"
        holdout.mkdir(parents=True)
        (holdout / "promptfooconfig.yaml").write_text("description: h\n")
        code, out = self.run_eval(
            ["--holdout"],
            env={
                "BETTERTERMS_HOLDOUT": "",
                "HOME": str(holdout.parent),
            },
        )
        self.assertEqual(code, 0, out)
        self.assertTrue((holdout / ".results" / "holdout-latest.json").is_file())
        self.assertFalse((self.evals / ".results").exists())


if __name__ == "__main__":
    unittest.main()
