"""The PreToolUse guard (spec 6.8): a best-effort deny on tool calls
whose input names a ``.floor`` file, a ``held/`` path, the ``held
approve`` or ``case set-floor`` commands, or the session transcript
directory. Anything else passes with no output.
"""

import json
import os
import subprocess
import sys
import unittest

from bt_helpers import REPO, BtTestCase

GUARD = REPO / "hooks" / "guard.py"
TRANSCRIPT = "/tmp/bt-guard-sess-9/transcript.jsonl"


def run_guard(tool_input, transcript_path=TRANSCRIPT):
    event = {
        "hook_event_name": "PreToolUse",
        "session_id": "s-1",
        "transcript_path": transcript_path,
        "cwd": "/tmp",
        "tool_name": "Bash",
        "tool_input": tool_input,
    }
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=30,
    )


def decision(proc):
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"guard did not print JSON\nstdout: {proc.stdout}\n"
            f"stderr: {proc.stderr}"
        )
    return out["hookSpecificOutput"]


class DenyTest(BtTestCase):
    def assert_denied(self, tool_input, needle=None):
        proc = run_guard(tool_input)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = decision(proc)
        self.assertEqual(out["permissionDecision"], "deny")
        if needle:
            self.assertIn(needle, out["permissionDecisionReason"])

    def test_guard_denies_floor_read(self):
        self.assert_denied(
            {"command": "cat ~/.betterterms/cases/x/.floor"},
            "floor",
        )

    def test_guard_denies_floor_in_nested_input(self):
        self.assert_denied(
            {"file_path": "/tmp/bt/cases/c-1/.floor"}
        )

    def test_guard_denies_held_write(self):
        self.assert_denied(
            {
                "file_path": "/tmp/bt/cases/c-1/held/"
                "abcd1234.approved"
            },
            "held",
        )

    def test_guard_denies_held_approve_command(self):
        self.assert_denied(
            {
                "command": "python3 bt.py held approve "
                "case-1 abcd1234"
            }
        )

    def test_guard_denies_case_set_floor_command(self):
        self.assert_denied(
            {"command": "python3 bt.py case set-floor case-1"}
        )

    def test_guard_denies_transcript_read(self):
        self.assert_denied(
            {"command": f"cat {TRANSCRIPT}"}, "session"
        )

    def test_guard_denies_transcript_dir_listing(self):
        self.assert_denied({"command": "ls /tmp/bt-guard-sess-9/"})


class AllowTest(BtTestCase):
    def assert_allowed(self, tool_input):
        proc = run_guard(tool_input)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_guard_allows_gate(self):
        self.assert_allowed(
            {
                "command": "python3 bt.py gate case-1 "
                "--draft d.yaml"
            }
        )

    def test_guard_allows_held_list(self):
        self.assert_allowed(
            {"command": "python3 bt.py held list case-1"}
        )

    def test_guard_allows_unrelated_paths(self):
        self.assert_allowed({"command": "ls /tmp/other"})
        self.assert_allowed({"file_path": "/tmp/notes.txt"})


if __name__ == "__main__":
    unittest.main()
