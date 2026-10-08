"""Prompt-hook hardening: word-amount floors, bounded and linear
scanning, and the fail-closed launcher.

A ``bt floor`` lookalike claims the walk-away with digits or with
number words, in any order and with or without a case id. Every
floor-path block suppresses the submitted text in the host's block
display where supported; local transcripts still record it, so the
reasons never echo it either. The shell wrapper turns a missing or
hung interpreter into an exit-2 block inside its own deadline, well
before the host's configured timeout would forward the prompt.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import unittest

from bt_helpers import REPO, BtTestCase
from test_prompt_commands import run_hook, hook_json

sys.path.insert(0, str(REPO / "hooks"))
import _scan  # noqa: E402

GUARD = REPO / "hooks" / "prompt-guard.sh"
SESSION_START = REPO / "hooks" / "session-start.sh"


def run_guard(home, prompt, python="python3", deadline=None):
    env = dict(
        os.environ,
        BETTERTERMS_HOME=str(home),
        CLAUDE_PLUGIN_ROOT=str(REPO),
        PYTHON=python,
    )
    if deadline is not None:
        env["BT_HOOK_DEADLINE"] = str(deadline)
    return subprocess.run(
        ["sh", str(GUARD)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def run_session_start(home, python="python3", plugin_root=REPO):
    env = dict(
        os.environ,
        BETTERTERMS_HOME=str(home),
        CLAUDE_PLUGIN_ROOT=str(plugin_root),
        PYTHON=python,
    )
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run(
        ["sh", str(SESSION_START)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class WordAmountFloorTest(BtTestCase):
    def make_case(self, cid="case-1"):
        d = self.home / "cases" / cid
        d.mkdir(parents=True)
        return d

    def test_word_amount_without_case_id_blocks(self):
        # `sixty two` claims the walk-away without a digit: the hook
        # used to pass it to the model. Glued forms, scale
        # abbreviations and stem words claim it the same way the
        # gate's word lists read them. Nothing is written or echoed.
        d = self.make_case()
        for prompt in (
            "bt floor sixty two",
            "bt floor sixtytwo",
            "bt floor twelvehundred",
            "bt floor a hundred dollars",
            "bt floor twok",
            "bt floor a mil",
            "bt floor fifty grand",
            "bt floor two lakh",
            "bt floor LXII",
            "set the bt floor to sixty",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                out = hook_json(proc)
                self.assertEqual(out["decision"], "block")
                self.assertNotIn("sixty", proc.stdout)
                self.assertNotIn("hundred", proc.stdout)
                self.assertNotIn("twok", proc.stdout)
                self.assertNotIn("lakh", proc.stdout)
                self.assertFalse((d / ".floor").exists())

    def test_word_amount_misordered_blocks(self):
        # The amount before the case id is still a floor attempt.
        d = self.make_case()
        proc = run_hook(self.home, "bt floor sixty two case-1")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("sixty", proc.stdout)
        self.assertFalse((d / ".floor").exists())

    def test_floor_blocks_suppress_the_original_prompt(self):
        # Where the host honors it, the block output does not carry
        # the submitted prompt's text. Local transcripts still record
        # it -- suppression is display-only -- so the block reason
        # itself never echoes the amount either.
        d = self.make_case()
        for prompt in (
            "bt floor case-1 62",
            "bt floor sixty two",
            "the bt floor amount is 62 dollars",
        ):
            with self.subTest(prompt=prompt):
                out = hook_json(run_hook(self.home, prompt))
                self.assertEqual(out["decision"], "block")
                self.assertTrue(
                    out["hookSpecificOutput"][
                        "suppressOriginalPrompt"
                    ]
                )

    def test_non_floor_blocks_stay_in_the_transcript(self):
        # Suppression is a floor-path privacy measure; an approve
        # usage block leaves the user's own words alone.
        self.make_case()
        proc = run_hook(self.home, "bt approve case-1 abcd1234 x y")
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("hookSpecificOutput", out)

    def test_prose_still_passes(self):
        # Number-word scanning must not widen the deny into ordinary
        # prose about the command: the listed exceptions and
        # lookalike letter runs are not amounts.
        self.make_case()
        for prompt in (
            "bt floor is set in the terminal",
            "the bt floor plan has no number in it",
            "the bt floor amount is often misread",
            "bt floor money stays private",
            "bt floor is a family matter",
            "bt floor acme-20261005-ab12",
        ):
            with self.subTest(prompt=prompt):
                proc = run_hook(self.home, prompt)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), "")


class UnicodeWordCharTest(BtTestCase):
    """The regexes the scanner emulates are Unicode-aware: \\w and
    \\b treat é as a word character, so an accented attribute key
    or tag suffix must not smuggle a floor payload out of scope."""

    def test_nonascii_attr_key_keeps_body_in_scope(self):
        # The key is éfrom, not from: the element is not
        # from="agent" and its body stays live for the floor rule.
        prompt = (
            '<wake><message éfrom="agent">'
            "bt floor sixty</message></wake>"
        )
        live = _scan.live_text(prompt)
        self.assertIn("bt floor sixty", live)
        self.assertTrue(_scan.floor_hit(live))

    def test_nonascii_suffix_is_no_message_opener(self):
        # <message\b needs a boundary after `message`: é is a word
        # character, so <messageé is plain text and the payload
        # inside stays live.
        prompt = (
            '<wake><messageé from="agent">'
            "bt floor sixty</messageé></wake>"
        )
        live = _scan.live_text(prompt)
        self.assertIn("bt floor sixty", live)
        self.assertTrue(_scan.floor_hit(live))

    def test_ascii_semantics_unchanged(self):
        # A plain from="agent" body still leaves scope, and a human
        # trigger body is still the user text.
        agent = '<message from="agent">bt floor sixty</message>'
        prompt = (
            "<wake>"
            + agent
            + '<message from="human" trigger="true">hi</message>'
            + "</wake>"
        )
        self.assertNotIn("bt floor sixty", _scan.live_text(prompt))
        self.assertEqual(_scan.user_text(prompt), "hi")


class GuardLauncherTest(BtTestCase):
    def test_dead_python_blocks_with_exit_2(self):
        # A missing interpreter used to fail open: the wrapper emits
        # a block and exits 2 so the host denies the prompt.
        proc = run_guard(
            self.home, "bt floor case-1 62", python="false"
        )
        self.assertEqual(proc.returncode, 2)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")

    def test_hook_failure_blocks_with_exit_2(self):
        # A Python that exits nonzero (import failure, killed check)
        # is the same fail-closed shape.
        proc = run_guard(
            self.home, "hello", python="/nonexistent-python"
        )
        self.assertEqual(proc.returncode, 2)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")

    def test_hook_output_passes_through(self):
        proc = run_guard(self.home, "bt floor case-9 62")
        self.assertEqual(proc.returncode, 0)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertIn("no such case", out["reason"])

    def test_silent_hook_passes(self):
        proc = run_guard(self.home, "please lower my bill")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_hung_check_blocks_before_the_host_deadline(self):
        # A wedged interpreter used to wait for the host timeout,
        # which forwards the prompt. The wrapper's own deadline kills
        # it and emits the static block instead.
        hung = self.tmp / "hung-python"
        hung.write_text("#!/bin/sh\nexec sleep 60\n")
        hung.chmod(0o755)
        started = time.monotonic()
        proc = run_guard(
            self.home,
            "bt floor case-1 62",
            python=str(hung),
            deadline=1,
        )
        self.assertLess(time.monotonic() - started, 9.9)
        self.assertEqual(proc.returncode, 2)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("62", proc.stdout)


class SessionStartPreflightTest(BtTestCase):
    def test_marker_only_when_the_check_runs(self):
        # The skills advertise typed commands on this marker, so a
        # dead interpreter must suppress it.
        proc = run_session_start(self.home, python="false")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("typed bt commands are active", proc.stdout)
        self.assertIn("prompt check failed", proc.stdout)

    def test_marker_prints_when_the_check_runs(self):
        proc = run_session_start(self.home)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("typed bt commands are active", proc.stdout)

    def test_marker_absent_without_the_runtime(self):
        # A plugin root holding only the hooks (no installed skills):
        # the {} parse path still works, but the runtime the commands
        # need does not, so the marker must stay off.
        root = self.tmp / "hooks-only"
        shutil.copytree(REPO / "hooks", root / "hooks")
        proc = run_session_start(self.home, plugin_root=root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("typed bt commands are active", proc.stdout)
        self.assertIn("prompt check failed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
