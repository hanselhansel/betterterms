"""The PreToolUse guard (spec 6.8), best effort.

Every rule is scoped to the betterterms data folder
(``$BETTERTERMS_HOME``, default ``~/.betterterms``): paths under it
pass only for the case files the skills write themselves or when the
whole Bash command is one ``bt.py`` invocation, while ``.floor``,
``held/``, ``ledger.jsonl`` and ``config.yaml`` plus the user-only
verbs stay denied either way. The session transcript's ``*.jsonl``
files are denied; sibling folders such as ``memory/`` are not. Paths
in unrelated projects are untouched.
"""

import json
import os
import subprocess
import sys
import unittest

from bt_helpers import REPO, BtTestCase

GUARD = REPO / "hooks" / "guard.py"
TRANSCRIPT = "/tmp/bt-guard-sess-9/transcript.jsonl"
BT_HOME = "/tmp/bt-home-9"


def run_guard(
    tool_input, transcript_path=TRANSCRIPT, home=BT_HOME, cwd="/tmp"
):
    event = {
        "hook_event_name": "PreToolUse",
        "session_id": "s-1",
        "transcript_path": transcript_path,
        "cwd": cwd,
        "tool_name": "Bash",
        "tool_input": tool_input,
    }
    env = dict(os.environ)
    if home is None:
        env.pop("BETTERTERMS_HOME", None)
    else:
        env["BETTERTERMS_HOME"] = home
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
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
    def assert_denied(self, tool_input, needle=None, **kw):
        proc = run_guard(tool_input, **kw)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = decision(proc)
        self.assertEqual(out["permissionDecision"], "deny")
        if needle:
            self.assertIn(needle, out["permissionDecisionReason"])

    def test_guard_denies_floor_read(self):
        self.assert_denied(
            {"command": f"cat {BT_HOME}/cases/x/.floor"},
            "floor",
        )

    def test_guard_denies_floor_under_default_home(self):
        # With no BETTERTERMS_HOME the default ~/.betterterms applies;
        # the tilde expands to the test's real HOME, only as a string.
        self.assert_denied(
            {"command": "cat ~/.betterterms/cases/x/.floor"},
            home=None,
        )

    def test_guard_denies_floor_in_nested_input(self):
        self.assert_denied(
            {"file_path": f"{BT_HOME}/cases/c-1/.floor"}
        )

    def test_guard_denies_dotdot_escape_into_home(self):
        self.assert_denied(
            {"file_path": "/tmp/elsewhere/../bt-home-9/cases/c/.floor"}
        )

    def test_guard_denies_held_write(self):
        self.assert_denied(
            {
                "file_path": f"{BT_HOME}/cases/c-1/held/"
                "abcd1234.approved"
            },
            "held",
        )

    def test_guard_denies_held_dir_listing(self):
        self.assert_denied({"command": f"ls {BT_HOME}/cases/c-1/held"})

    def test_guard_denies_ledger_and_config(self):
        self.assert_denied({"command": f"cat {BT_HOME}/ledger.jsonl"})
        self.assert_denied({"command": f"cat {BT_HOME}/config.yaml"})

    def test_guard_denies_home_listing_and_recursive_read(self):
        self.assert_denied({"command": f"ls {BT_HOME}"})
        self.assert_denied(
            {"command": f"grep -r offer {BT_HOME}/cases"}
        )
        self.assert_denied(
            {"path": f"{BT_HOME}/cases", "pattern": "**/*.floor"}
        )

    def test_guard_denies_held_approve_command(self):
        self.assert_denied(
            {
                "command": "python3 bt.py held approve "
                "case-1 abcd1234"
            }
        )

    def test_guard_denies_held_reject_command(self):
        self.assert_denied(
            {"command": "python3 bt.py held reject case-1 abcd1234"}
        )

    def test_guard_denies_case_set_floor_command(self):
        self.assert_denied(
            {"command": "python3 bt.py case set-floor case-1"}
        )

    def test_guard_denies_split_argv_user_verb(self):
        # A command split into argv pieces still names the verb.
        self.assert_denied(
            {"argv": ["python3", "bt.py", "held", "approve", "c", "h"]}
        )

    def test_guard_denies_user_verb_via_env_prefix(self):
        self.assert_denied(
            {
                "command": f"BETTERTERMS_HOME={BT_HOME} python3 bt.py "
                "case set-floor case-1"
            }
        )

    def test_guard_denies_bt_invocation_touching_protected(self):
        # A pure bt.py call may not point its file args at .floor.
        self.assert_denied(
            {
                "command": "python3 bt.py gate case-1 --draft "
                f"{BT_HOME}/cases/case-1/.floor"
            }
        )

    def test_guard_normalizes_quotes_and_ifs(self):
        self.assert_denied(
            {"command": f'cat {BT_HOME}/cases/x/".floor"'}
        )
        self.assert_denied(
            {"command": f"cat$IFS{BT_HOME}/cases/x/.floor"}
        )
        self.assert_denied(
            {"command": f"cat {BT_HOME}/cases/x/\\.floor"}
        )
        self.assert_denied(
            {"command": f'cat "$BETTERTERMS_HOME"/cases/x/held/h.yaml'}
        )

    def test_guard_denies_cwd_relative_paths_inside_home(self):
        case_cwd = f"{BT_HOME}/cases/c-1"
        self.assert_denied({"command": "cat .floor"}, cwd=case_cwd)
        self.assert_denied(
            {"command": "cat held/abcd1234.yaml"}, cwd=case_cwd
        )

    def test_guard_denies_transcript_read(self):
        self.assert_denied(
            {"command": f"cat {TRANSCRIPT}"}, "session"
        )

    def test_guard_denies_sibling_jsonl_and_glob(self):
        self.assert_denied(
            {"command": "cat /tmp/bt-guard-sess-9/other.jsonl"}
        )
        self.assert_denied(
            {"command": "cat /tmp/bt-guard-sess-9/*.jsonl"}
        )


class AllowTest(BtTestCase):
    def assert_allowed(self, tool_input, **kw):
        proc = run_guard(tool_input, **kw)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_guard_allows_gate(self):
        self.assert_allowed(
            {
                "command": "python3 bt.py gate case-1 "
                "--draft d.yaml"
            }
        )

    def test_guard_allows_bt_invocation_naming_home(self):
        self.assert_allowed(
            {
                "command": "python3 bt.py gate case-1 --draft "
                f"{BT_HOME}/cases/case-1/draft.yaml"
            }
        )
        self.assert_allowed(
            {
                "command": f"BETTERTERMS_HOME={BT_HOME} python3 "
                "bt.py case show case-1"
            }
        )

    def test_guard_allows_held_list(self):
        self.assert_allowed(
            {"command": "python3 bt.py held list case-1"}
        )

    def test_guard_allows_case_file_writes(self):
        for name in (
            "brief.yaml",
            "plan.yaml",
            "draft.yaml",
            "inbound.yaml",
            "gate.json",
            "thread.md",
            "sources/ref.md",
        ):
            with self.subTest(name=name):
                self.assert_allowed(
                    {
                        "file_path": f"{BT_HOME}/cases/c-1/{name}",
                        "content": "x",
                    }
                )

    def test_guard_allows_case_file_read_in_home_cwd(self):
        self.assert_allowed(
            {"command": "cat draft.yaml"},
            cwd=f"{BT_HOME}/cases/c-1",
        )

    def test_guard_ignores_unrelated_projects(self):
        # Scope: held/, .floor and cases/ outside the betterterms
        # home are somebody else's files (review finding 8).
        self.assert_allowed({"file_path": "/proj/a/held/x.yaml"})
        self.assert_allowed({"file_path": "/proj/x/.floor"})
        self.assert_allowed({"command": "ls /tmp/other/held"})
        self.assert_allowed({"command": "cat /proj/notes/.floor"})

    def test_guard_allows_transcript_dir_and_memory(self):
        # Only the session's own *.jsonl files are off limits; the
        # folder listing and the memory/ folder are not (finding 8).
        self.assert_allowed({"command": "ls /tmp/bt-guard-sess-9/"})
        self.assert_allowed(
            {"command": "cat /tmp/bt-guard-sess-9/memory/notes.md"}
        )

    def test_guard_allows_unrelated_paths(self):
        self.assert_allowed({"command": "ls /tmp/other"})
        self.assert_allowed({"file_path": "/tmp/notes.txt"})


if __name__ == "__main__":
    unittest.main()
