"""Betterterms PreToolUse guard hook tests.

The hook is exercised as a subprocess exactly the way the harness
runs it: JSON on stdin, hookSpecificOutput on stdout. Free-text
fields are never scanned; commands naming the home or the private
names pass only as one plain
``python3 <.../betterterms-guardrails/scripts/bt.py> <args>`` call.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "hooks" / "guard.py"
BT = Path(__file__).resolve().parents[1] / "skills" / "betterterms-guardrails" / "scripts" / "bt.py"
BT_HOME = "/tmp/bt-home-9"
CASE = f"{BT_HOME}/cases/case-1"
TRANSCRIPT = "/tmp/bt-guard-sess-9/transcript.jsonl"


def run_guard(tool_input, cwd="/tmp", tool_name="Bash",
              transcript_path=TRANSCRIPT):
    event = {
        "session_id": "s",
        "transcript_path": transcript_path,
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_use_id": "t",
        "tool_input": tool_input,
    }
    env = dict(os.environ, BETTERTERMS_HOME=BT_HOME)
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout or "{}")


class GuardCase(unittest.TestCase):
    def assert_allowed(self, tool_input, **kw):
        self.assertEqual(run_guard(tool_input, **kw), {})

    def assert_denied(self, tool_input, needle=None, **kw):
        out = run_guard(tool_input, **kw)
        extra = out["hookSpecificOutput"]
        self.assertEqual(extra["permissionDecision"], "deny")
        if needle:
            self.assertIn(needle, extra["permissionDecisionReason"])

    def test_guard_ignores_malformed_hook_input(self):
        for raw in (
            "", "not json", '"a string"',
            '{"tool_input": "nope"}', '{"tool_input": 3}',
        ):
            proc = subprocess.run(
                [sys.executable, str(GUARD)],
                input=raw, capture_output=True, text=True,
                env=dict(os.environ, BETTERTERMS_HOME=BT_HOME), timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout or "{}"), {})


class AllowTest(GuardCase):
    def test_guard_allows_normal_usage(self):
        self.assert_allowed({"command": "cat /tmp/x"})
        self.assert_allowed({"file_path": f"{CASE}/brief.yaml"},
                            tool_name="Read")
        self.assert_allowed({"path": "/proj", "pattern": "*.md"},
                            tool_name="Glob")
        self.assert_allowed({"file_path": "/tmp/notes.md"},
                            tool_name="Write")

    def test_guard_allows_strict_gate_call(self):
        # The whole raw command is one plain bt.py call: the charset
        # admits paths and flags but no shell syntax.
        self.assert_allowed(
            {"command": f"python3 {BT} gate case-1 --draft {CASE}/draft.yaml"})
        self.assert_allowed(
            {"command": f"python3 {BT} gate case-1 --draft {CASE}/draft.yaml"
                        f" --inbound {CASE}/inbound.yaml --approved"})

    def test_guard_allows_strict_bt_subcommands(self):
        for sub in (
            "held list case-1",
            "case new --pack bills --mode act --direction pay",
            "case set-terms case-1 --target 60",
            "score case-1 --inbound /tmp/i.yaml",
            "ledger add case-1 --before 100 --after 90 --period month",
        ):
            self.assert_allowed({"command": f"python3 {BT} {sub}"})

    def test_guard_allows_case_file_reads(self):
        for name in (
            "brief.yaml", "plan.yaml", "draft.yaml", "inbound.yaml",
            "gate.json", "thread.md", "sources/rates.md",
            "inbox/statement.pdf", "inbox",
        ):
            self.assert_allowed({"file_path": f"{CASE}/{name}"},
                                tool_name="Read")

    def test_guard_allows_case_file_writes(self):
        for name in ("draft.yaml", "inbound.yaml", "thread.md",
                     "sources/rates.md"):
            self.assert_allowed({"file_path": f"{CASE}/{name}"},
                                tool_name="Write")

    def test_guard_allows_glob_and_grep_on_allowed_dirs(self):
        self.assert_allowed(
            {"path": f"{CASE}/inbox", "pattern": "*.pdf"}, tool_name="Glob")
        self.assert_allowed(
            {"path": f"{CASE}/sources", "glob": "*.md"}, tool_name="Grep")
        self.assert_allowed(
            {"pattern": f"{CASE}/inbox/*.pdf"}, tool_name="Glob")

    def test_guard_allows_read_in_home_cwd_when_command_names_nothing(self):
        # A command only denies when it names the home or a private
        # name; a bare relative read inside a case dir names neither.
        self.assert_allowed({"command": "cat draft.yaml"}, cwd=CASE)

    def test_guard_ignores_free_text_fields(self):
        # content, new_string, old_string, description and prompt are
        # never scanned, even when they name the home or private files.
        text = f"mention {BT_HOME}/.floor and held/ and bt.py"
        self.assert_allowed(
            {"file_path": "/tmp/notes.md", "content": text},
            tool_name="Write")
        self.assert_allowed(
            {"file_path": "/tmp/notes.md", "old_string": "a",
             "new_string": text}, tool_name="Edit")
        self.assert_allowed({"command": "ls", "description": text})
        self.assert_allowed({"prompt": text}, tool_name="Task")

    def test_guard_allows_unrelated_project_paths(self):
        self.assert_allowed({"file_path": "/proj/a/held/x.yaml"},
                            tool_name="Read")
        self.assert_allowed({"file_path": "/proj/x/.floor"},
                            tool_name="Write")
        self.assert_allowed({"path": "/tmp/other/held"}, tool_name="Read")

    def test_guard_allows_transcript_dir_and_memory(self):
        # Only transcript *.jsonl files are off limits; the folder
        # itself, non-jsonl names and memory/ subdirs pass.
        tdir = os.path.dirname(TRANSCRIPT)
        self.assert_allowed({"command": f"ls {tdir}/"})
        self.assert_allowed({"command": f"cat {tdir}/debug.log"})
        self.assert_allowed({"command": f"cat {tdir}/memory/notes.md"})


class DenyTest(GuardCase):
    def test_guard_denies_review_bypasses(self):
        # Every bypass shape the second review found: the command
        # names the home or a private name but is not one plain bt.py
        # call, so the whole raw command is denied.
        for cmd in (
            "cat held/$V.yaml",                  # held $V
            "V=.floor; cat $V",                  # variable indirection
            "python3 b?.py held approve c h",    # b?.py glob
            "cd ~ && touch .betterterms/x",      # cd + chained touch
            f"python3 {BT} gate c --draft d.yaml\nrm {BT_HOME}/x",
            f"cat $(ls {BT_HOME})",              # $(...)
            f'python3 "{BT}" gate case-1',       # quotes
            "cat `ls held`",                     # backticks
            f"python3 {BT} gate c | tee {BT_HOME}/x",
            f"python3 {BT} gate c > {BT_HOME}/gate.json",
            f"cd {BT_HOME} && cat ledger.jsonl",
            "ls $HOME/.betterterms",
            "cat $BETTERTERMS_HOME/cases/case-1/held/x.yaml",
            "cat ${BETTERTERMS_HOME}/.floor",
        ):
            with self.subTest(cmd=cmd):
                self.assert_denied({"command": cmd})

    def test_guard_denies_user_verbs_even_in_strict_shape(self):
        # Approve, reject and set-floor are user actions; the strict
        # shape does not rescue them, in any spelling of the path.
        for cmd in (
            f"python3 {BT} held approve case-1 abcd1234",
            f"python3 {BT} held reject case-1 abcd1234",
            f"python3 {BT} case set-floor case-1 60",
            f"python3 {BT} case set-floor case-1 --usd 60",
        ):
            self.assert_denied({"command": cmd}, "user")
        # Split argv, env prefixes and relative paths deny too.
        self.assert_denied(
            {"argv": ["python3", "bt.py", "held", "approve", "c", "h"]})
        self.assert_denied(
            {"command": f"BETTERTERMS_HOME={BT_HOME} python3 {BT}"
                        " held approve c h"})
        self.assert_denied(
            {"command": "python3 bt.py held approve case-1 abcd1234"})
        self.assert_denied(
            {"command": f"python3 {BT} case --set-floor case-1 60"})

    def test_guard_denies_non_strict_bt_paths(self):
        # Only <.../betterterms-guardrails/scripts/bt.py> may run.
        for cmd in (
            "python3 bt.py gate case-1 --draft d.yaml",
            "python3 ./bt.py gate case-1",
            "python3 /x/scripts/bt.py gate case-1",
            "python3 /x/betterterms-guardrails/scripts/bt.py2 gate c",
            f"python3\t{BT} gate case-1",
            f"python3  {BT} gate case-1",
            f"python3 {BT}/../scripts/bt.py gate c",
            "python bt.py gate case-1",
        ):
            with self.subTest(cmd=cmd):
                self.assert_denied({"command": cmd})

    def test_guard_denies_command_reads_via_home_paths(self):
        # Bash cannot reach case files by naming them; file tools can.
        self.assert_denied({"command": f"cat {CASE}/brief.yaml"})
        self.assert_denied({"command": f"cat {BT_HOME}/config.yaml"})
        self.assert_denied({"command": f"ls {BT_HOME}"})
        self.assert_denied({"command": f"grep -r offer {BT_HOME}/cases"})
        self.assert_denied({"command": f"ls {CASE}/held"})
        self.assert_denied({"command": f"cat {CASE}/draft.yaml"})

    def test_guard_denies_cwd_relative_private_names(self):
        # cd'd or not, the names held and .floor trigger on their own.
        self.assert_denied({"command": "cat .floor"}, cwd=CASE)
        self.assert_denied({"command": "cat held/x.yaml"}, cwd=CASE)
        self.assert_denied({"command": "cat ../case-2/.floor"}, cwd=CASE)
        self.assert_denied({"command": "ls held"}, cwd=CASE)

    def test_guard_denies_protected_paths(self):
        for path in (
            f"{CASE}/held/abcd.yaml", f"{CASE}/held/x.approved",
            f"{CASE}/.floor", f"{CASE}/x/.floor", f"{CASE}/held",
            f"{BT_HOME}/ledger.jsonl", f"{BT_HOME}/config.yaml",
        ):
            self.assert_denied({"file_path": path}, "floor",
                               tool_name="Read")
            self.assert_denied({"file_path": path}, tool_name="Write")

    def test_guard_denies_other_home_writes(self):
        # gate.json is verdict output; brief/plan belong to the user
        # or bt.py; inbox files are user drops. Nothing else writes.
        for name in ("gate.json", "brief.yaml", "plan.yaml",
                     "inbox/x.pdf", "notes.md"):
            self.assert_denied({"file_path": f"{CASE}/{name}"},
                               tool_name="Write")

    def test_guard_denies_other_home_reads(self):
        self.assert_denied({"file_path": BT_HOME}, tool_name="Read")
        self.assert_denied({"file_path": f"{BT_HOME}/cases"},
                           tool_name="Read")
        self.assert_denied({"file_path": CASE}, tool_name="Read")
        self.assert_denied({"file_path": f"{CASE}/unknown.yaml"},
                           tool_name="Read")
        self.assert_denied({"file_path": f"{CASE}/held/x"},
                           tool_name="Read")
        self.assert_denied(
            {"path": f"{BT_HOME}/cases", "pattern": "**/*.floor"},
            tool_name="Glob")

    def test_guard_denies_pattern_escapes(self):
        self.assert_denied(
            {"path": f"{CASE}/inbox", "pattern": "../.floor"},
            tool_name="Glob")
        self.assert_denied(
            {"pattern": "../.floor", "path": CASE}, tool_name="Grep")

    def test_guard_denies_session_transcript(self):
        tdir = os.path.dirname(TRANSCRIPT)
        self.assert_denied({"command": f"cat {TRANSCRIPT}"}, "session log")
        self.assert_denied({"command": f"cat {tdir}/other.jsonl"},
                           "session log")
        self.assert_denied({"command": f"cat {tdir}/*.jsonl"},
                           "session log")
        self.assert_denied({"file_path": TRANSCRIPT}, "session log",
                           tool_name="Read")
        self.assert_denied({"file_path": f"{tdir}/x.jsonl"},
                           "session log", tool_name="Read")

    def test_guard_denies_transcript_via_env(self):
        tdir = os.path.dirname(TRANSCRIPT)
        self.assert_denied(
            {"command": f'cat "$CLAUDE_TRANSCRIPT"/x.jsonl # {tdir}'},
            "session log")

    def test_guard_denies_quoting_and_expansion_tricks(self):
        # No shell parsing: the raw text names private names or the
        # home and is not the strict shape, so it denies untouched.
        for cmd in (
            f"cat{BT_HOME}/cases/x/\".floor\"",
            f"cat$IFS{BT_HOME}/cases/x/.floor",
            f"cat {BT_HOME}/cases/x/\\.floor",
            f'cat "$BETTERTERMS_HOME"/cases/x/held/h.yaml',
        ):
            with self.subTest(cmd=cmd):
                self.assert_denied({"command": cmd})


if __name__ == "__main__":
    unittest.main()
