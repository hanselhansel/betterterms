"""Tests for the promptfoo side of scripts/eval: --dev and --holdout.

--smoke stays in test_eval_harness.py. These tests load a temp copy of
scripts/eval, stub subprocess.run and shutil.which on it, and call
main() in-process.
"""

import contextlib
import io
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from test_eval_harness import _copy_repo, _load_eval


class PromptfooRunner(unittest.TestCase):
    """--dev/--holdout spawn promptfoo with evals/ as the working
    directory and hand -c a path relative to it, so the bare SDK
    packages the providers load resolve from evals/node_modules while
    file:// references still resolve against each config's directory."""

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
            return types.SimpleNamespace(returncode=0)

        real_subprocess, real_shutil = self.mod.subprocess, self.mod.shutil
        self.addCleanup(setattr, self.mod, "subprocess", real_subprocess)
        self.addCleanup(setattr, self.mod, "shutil", real_shutil)
        self.mod.subprocess = types.SimpleNamespace(run=fake_run)
        self.mod.shutil = types.SimpleNamespace(
            which=lambda name: "/fake/bin/promptfoo"
        )

    def run_eval(self, argv, env=None):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), \
                contextlib.redirect_stdout(out):
            code = self.mod.main(argv)
        return code, out.getvalue()

    def make_node_modules(self):
        (self.evals / "node_modules").mkdir()

    def test_dev_runs_promptfoo_inside_evals(self):
        self.make_node_modules()
        code, out = self.run_eval(["--dev"])
        self.assertEqual(code, 0, out)
        (argv, cwd), = self.calls
        self.assertEqual(cwd, self.evals)
        self.assertEqual(argv[:4], ["promptfoo", "eval", "-c", "promptfooconfig.yaml"])
        self.assertIn("--no-progress-bar", argv)

    def test_dev_needs_evals_node_modules(self):
        code, out = self.run_eval(["--dev"])
        self.assertEqual(code, 2, out)
        self.assertIn("npm ci --prefix evals", out)
        self.assertEqual(self.calls, [])

    def test_dev_needs_promptfoo_on_path(self):
        self.make_node_modules()
        self.mod.shutil = types.SimpleNamespace(which=lambda name: None)
        code, out = self.run_eval(["--dev"])
        self.assertEqual(code, 2, out)
        self.assertIn("promptfoo not installed", out)
        self.assertEqual(self.calls, [])

    def test_dev_passes_through_exit_code_and_prints_pass_rate(self):
        self.make_node_modules()

        def fake(argv, cwd=None, **_kw):
            Path(argv[argv.index("-o") + 1]).write_text(
                '{"results": {"stats": {"successes": 3, "failures": 1, '
                '"errors": 0}}}'
            )
            return types.SimpleNamespace(returncode=7)

        self.mod.subprocess = types.SimpleNamespace(run=fake)
        code, out = self.run_eval(["--dev"])
        self.assertEqual(code, 7)
        self.assertIn("pass rate: 3/4 (75.0%)", out)

    def test_holdout_config_reaches_c_relative_to_evals(self):
        self.make_node_modules()
        holdout = self.root.parent / "holdout"
        holdout.mkdir()
        config = holdout / "promptfooconfig.yaml"
        config.write_text("description: holdout\n")
        code, out = self.run_eval(
            ["--holdout"], env={"BETTERTERMS_HOLDOUT": str(holdout)}
        )
        self.assertEqual(code, 0, out)
        (argv, cwd), = self.calls
        self.assertEqual(cwd, self.evals)
        rel = argv[argv.index("-c") + 1]
        self.assertFalse(Path(rel).is_absolute())
        self.assertEqual((self.evals / rel).resolve(), config)

    def test_holdout_missing_config_exits_2(self):
        code, out = self.run_eval(
            ["--holdout"],
            env={"BETTERTERMS_HOLDOUT": str(self.root.parent / "nope")},
        )
        self.assertEqual(code, 2, out)
        self.assertIn("no holdout config", out)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
