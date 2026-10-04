"""The UserPromptSubmit hook's fail-closed paths (spec 6.8): an
unreadable event, a raised handler and a wedged bt.py subprocess all
block the prompt rather than let a possible ``bt`` line through.
Split from test_prompt_commands.py under the 400-line cap."""

import json
import os
import subprocess
import sys
import unittest

from bt_helpers import REPO
from test_prompt_commands import (
    HOOK,
    HookCase,
    hook_json,
    run_hook,
)
import prompt_commands  # noqa: E402


def run_hook_raw(home, raw_stdin):
    env = dict(
        os.environ,
        BETTERTERMS_HOME=str(home),
        CLAUDE_PLUGIN_ROOT=str(REPO),
    )
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw_stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class FailClosedTest(HookCase):
    def test_unparseable_event_blocks(self):
        # The hook fails closed: an event it cannot read may hide a
        # `bt floor` line, so nothing falls through to the model.
        proc = run_hook_raw(self.home, "{not json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")

    def test_hook_exception_blocks_not_passes(self):
        # A case dir that cannot be listed raises inside _handle;
        # the failure blocks the prompt instead of forwarding it.
        d = self.make_case()
        (d / ".floor").write_text("1.00")
        os.chmod(d, 0o000)
        try:
            proc = run_hook(self.home, "bt floor case-1 62")
        finally:
            os.chmod(d, 0o700)
        self.assertEqual(proc.returncode, 0)
        out = hook_json(proc)
        self.assertEqual(out["decision"], "block")

    def test_handle_exception_blocks_in_process(self):
        import io
        from unittest import mock

        event = json.dumps({"prompt": "bt floor case-1 62"})
        buf = io.StringIO()
        with (
            mock.patch("sys.stdin", io.StringIO(event)),
            mock.patch("sys.stdout", buf),
            mock.patch.object(
                prompt_commands, "_handle",
                side_effect=RuntimeError("boom"),
            ),
        ):
            prompt_commands.main()
        self.assertEqual(
            json.loads(buf.getvalue())["decision"], "block"
        )

    def test_bt_subprocess_timeout_is_seven_seconds(self):
        # The UserPromptSubmit hook budget is 10s; bt.py gets 7 so a
        # wedged subprocess still fails closed inside the limit.
        from unittest import mock

        seen = []

        def fake_run(argv, **kwargs):
            seen.append(kwargs.get("timeout"))
            return subprocess.CompletedProcess(
                argv, 0, stdout='{"ok": true}', stderr=""
            )

        with mock.patch.object(
            prompt_commands.subprocess, "run", side_effect=fake_run
        ):
            prompt_commands._run_bt(["where"])
        self.assertEqual(seen, [7])

    def test_hung_bt_blocks_the_prompt(self):
        # A bt.py that never answers must block, not wedge: the
        # TimeoutExpired lands in main's fail-closed catch.
        import io
        from unittest import mock

        self.make_case()
        event = json.dumps({"prompt": "bt floor case-1 62"})
        buf = io.StringIO()
        with (
            mock.patch("sys.stdin", io.StringIO(event)),
            mock.patch("sys.stdout", buf),
            mock.patch.object(
                prompt_commands.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("bt.py", 7),
            ),
        ):
            prompt_commands.main()
        self.assertEqual(
            json.loads(buf.getvalue())["decision"], "block"
        )


if __name__ == "__main__":
    unittest.main()
