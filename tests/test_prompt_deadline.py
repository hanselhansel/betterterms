"""The prompt-guard launcher's own deadline and descriptor hygiene.

The host's configured UserPromptSubmit timeout only discards a late
hook's output and forwards the prompt, so prompt-guard.sh bounds the
check itself: a hung interpreter, import, read or spawned child dies
at the inner deadline and the wrapper emits a static exit-2 block
comfortably before the host would forward. The descriptor detach is
what makes a fast check fast: a background watcher inheriting the
caller's output pipe kept even a clean run open for the whole
deadline.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from bt_helpers import REPO, BtTestCase
from test_prompt_commands import hook_json
from test_prompt_security import run_guard

SCRIPT_DIR = REPO / "hooks" / "prompt_commands.py"


def hung_python(tmp):
    fake = tmp / "hung-python"
    fake.write_text("#!/bin/sh\nexec sleep 60\n")
    fake.chmod(0o755)
    return str(fake)


class DeadlineTest(BtTestCase):
    """Wall-clock and process-tree behavior of the inner deadline."""

    def test_clean_pass_returns_fast(self):
        # Without the descriptor detach the watcher's sleep held the
        # caller's pipe open for the full deadline; a passing check
        # must answer in milliseconds.
        started = time.monotonic()
        proc = run_guard(self.home, "please lower my bill")
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_static_floor_block_returns_fast(self):
        (self.home / "cases" / "case-1").mkdir(parents=True)
        started = time.monotonic()
        proc = run_guard(self.home, "bt floor case-1 62")
        self.assertLess(time.monotonic() - started, 3.0)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("62", proc.stdout)

    def test_default_deadline_kills_a_hung_check(self):
        # Real deadline evidence: the check hangs and the wrapper
        # blocks at the ~8s default, inside the host's 10s forward.
        (self.home / "cases" / "case-1").mkdir(parents=True)
        started = time.monotonic()
        proc = run_guard(
            self.home, "bt floor case-1 62",
            python=hung_python(self.tmp),
        )
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 7.5)
        self.assertLess(elapsed, 10.0)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(hook_json(proc)["decision"], "block")
        self.assertNotIn("62", proc.stdout)

    def test_override_cannot_stretch_past_the_cap(self):
        # A caller override may only shorten: out-of-range, zero,
        # non-numeric and integer-width-busting values all land back
        # on the ~8s default, still inside the host's 10s forward.
        # The huge literal matters: an integer compare errors on it
        # yet keeps the value, stretching the wait past the host.
        hung = hung_python(self.tmp)
        for value in (
            "99",
            "0",
            "junk",
            "999999999999999999999999999999",
        ):
            with self.subTest(value=value):
                started = time.monotonic()
                proc = run_guard(
                    self.home, "please lower my bill",
                    python=hung, deadline=value,
                )
                elapsed = time.monotonic() - started
                self.assertGreaterEqual(elapsed, 7.5)
                self.assertLess(elapsed, 10.0)
                self.assertEqual(proc.returncode, 2)

    def test_short_override_is_honored(self):
        started = time.monotonic()
        proc = run_guard(
            self.home, "please lower my bill",
            python=hung_python(self.tmp), deadline=2,
        )
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 1.9)
        self.assertLess(elapsed, 5.0)
        self.assertEqual(proc.returncode, 2)

    def test_timed_out_check_leaves_no_child_to_finish(self):
        # A timed-out child tree dies with its parent: a write staged
        # under the hung check must never land after the block.
        marker = self.tmp / "staged-marker"
        fake = self.tmp / "slow-python"
        fake.write_text(
            "#!/bin/sh\n"
            f'( sleep 3; touch "{marker}" ) &\n'
            "exec sleep 60\n"
        )
        fake.chmod(0o755)
        proc = run_guard(
            self.home, "bt approve case-1 deadbeef",
            python=str(fake), deadline=1,
        )
        self.assertEqual(proc.returncode, 2)
        time.sleep(3.5)
        self.assertFalse(marker.exists())


class MissingRuntimeTest(BtTestCase):
    """A plugin root with hooks but no runtime still fails closed:
    the static block never echoes the typed amount or approval hash.
    """

    def hooks_only_root(self):
        root = self.tmp / "hooks-only"
        shutil.copytree(REPO / "hooks", root / "hooks")
        return root

    def run_hook(self, root, prompt):
        env = dict(
            os.environ,
            BETTERTERMS_HOME=str(self.home),
            CLAUDE_PLUGIN_ROOT=str(root),
        )
        env.pop("CLAUDE_PROJECT_DIR", None)
        return subprocess.run(
            [sys.executable, str(root / "hooks" / "prompt_commands.py")],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_approve_blocks_without_the_runtime(self):
        proc = self.run_hook(self.hooks_only_root(), "bt approve case-1 deadbeef")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("cannot reach the bt.py runtime", out["reason"])
        self.assertNotIn("deadbeef", proc.stdout)

    def test_floor_blocks_without_the_runtime(self):
        proc = self.run_hook(self.hooks_only_root(), "bt floor case-1 62")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("cannot reach the bt.py runtime", out["reason"])
        self.assertNotIn("62", proc.stdout)


if __name__ == "__main__":
    unittest.main()
