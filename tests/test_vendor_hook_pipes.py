"""vendor-into-repo compound-command handling of the owned old
hook: a safe compound is rewired invocation-by-invocation with the
user's other commands, order, quoting and entry fields intact,
while an owned invocation on either side of a single ``|`` cannot
be safely rewritten at all -- the guarded launch would hide its
block exit downstream and the ``true`` no-op would starve the
neighbour's stream -- so the run refuses before any write.
"""

import json
import tempfile
import unittest
from pathlib import Path

from test_install import make_repo, run

PROMPT_CMD = (
    'bash "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
    'prompt-guard.sh"'
)
# The command the pre-guard vendor run registered; re-vendoring must
# rewire it to the guarded launcher, not leave it running unguarded.
OLD_PROMPT_CMD = (
    'python3 "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
    'prompt_commands.py"'
)


def settings_with(command, *extra_commands):
    return json.dumps(
        {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "kept",
                        "hooks": [
                            {"type": "command", "command": command}
                        ]
                        + [
                            {"type": "command", "command": c}
                            for c in extra_commands
                        ],
                    }
                ]
            }
        }
    )


class VendorPipeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = make_repo(self.tmp)
        self.target = self.tmp / "consumer"
        self.target.mkdir()
        self.settings = self.target / ".claude" / "settings.json"

    def vendor(self, *args):
        return run(self.repo, "vendor-into-repo", str(self.target), *args)

    def write_settings(self, raw):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(raw, encoding="utf-8")

    def commands(self, event):
        """The command strings registered under ``hooks.<event>``."""
        return [
            h["command"]
            for entry in json.loads(
                self.settings.read_text(encoding="utf-8")
            )["hooks"][event]
            for h in entry["hooks"]
        ]

    def test_guarded_present_keeps_compound_command(self):
        # The guarded hook is already registered and the old owned
        # invocation sits inside a compound command with quoted data:
        # only that invocation is neutralized to ``true`` -- the
        # user's other commands, order, quoting and the entry's
        # fields all survive, and no data is dropped.
        compound = (
            'echo "a | pipe in data" && '
            + OLD_PROMPT_CMD
            + ' --flag && echo after'
        )
        self.write_settings(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "matcher": "kept",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": compound,
                                        "timeout": 7,
                                    },
                                    {
                                        "type": "command",
                                        "command": PROMPT_CMD,
                                    },
                                ],
                            }
                        ]
                    }
                }
            )
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        read = json.loads(self.settings.read_text(encoding="utf-8"))
        entry = read["hooks"]["UserPromptSubmit"][0]
        self.assertEqual(entry["matcher"], "kept")
        hooks = entry["hooks"]
        self.assertEqual(len(hooks), 2)
        self.assertEqual(
            hooks[0]["command"],
            'echo "a | pipe in data" && true --flag && echo after',
        )
        self.assertEqual(hooks[0]["timeout"], 7)
        self.assertEqual(hooks[1]["command"], PROMPT_CMD)

    def test_compound_migration_rewires_only_the_invocation(self):
        # No guarded hook yet and the old owned invocation sits in a
        # compound command carrying quoted pipe-looking data: that
        # invocation becomes the guarded launch, the surrounding
        # commands and quoting stay, and a re-run does not change
        # the file again.
        compound = (
            'echo "a | pipe in data" && '
            + OLD_PROMPT_CMD
            + " && echo after"
        )
        self.write_settings(settings_with(compound))
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(
            self.commands("UserPromptSubmit"),
            [f'echo "a | pipe in data" && {PROMPT_CMD} && echo after'],
        )
        first = self.settings.read_text(encoding="utf-8")
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), first)

    def test_piped_owned_hook_refuses_before_any_write(self):
        # An owned invocation on either side of a single | can
        # neither migrate (the guarded block exit would sit
        # mid-pipe, masked downstream) nor neutralize (the
        # neighbour's stream would silently change). The run
        # refuses BEFORE copying skills/hooks or touching settings:
        # nonzero exit, the unsafe command reported, settings bytes
        # and existing files exactly as they were.
        for cmd in (
            f"{OLD_PROMPT_CMD} | cat",
            f"cat transcript | {OLD_PROMPT_CMD}",
            f"echo hi && {OLD_PROMPT_CMD} | logger -t bt",
            f"{OLD_PROMPT_CMD} --flag | cat",
            f"{OLD_PROMPT_CMD} > hook.log | cat",
            f"{OLD_PROMPT_CMD} 2>&1 | cat",
            f"echo one | cat && {OLD_PROMPT_CMD} | sed s/x/y/",
        ):
            with self.subTest(cmd=cmd):
                self.write_settings(settings_with(cmd))
                raw = self.settings.read_text(encoding="utf-8")
                proc = self.vendor()
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("piped owned prompt hook", proc.stderr)
                self.assertIn(cmd, proc.stderr)
                self.assertEqual(
                    self.settings.read_text(encoding="utf-8"), raw
                )
                self.assertFalse(
                    (self.target / ".claude" / "skills").exists()
                )
                self.settings.unlink()

    def test_piped_old_hook_with_guard_present_still_refuses(self):
        # The guarded entry being registered does not make a piped
        # old invocation safe to drop: same refuse-before-write.
        piped = f"{OLD_PROMPT_CMD} | logger -t bt"
        self.write_settings(settings_with(piped, PROMPT_CMD))
        raw = self.settings.read_text(encoding="utf-8")
        proc = self.vendor()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("piped owned prompt hook", proc.stderr)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), raw)

    def test_supported_compound_still_migrates(self):
        # ||, &&, a plain redirect, and an unrelated pipeline feeding
        # a later && are all safe: the invocation is replaced and
        # the shape preserved.
        for compound, want in (
            (
                f"echo a || {OLD_PROMPT_CMD}",
                f"echo a || {PROMPT_CMD}",
            ),
            (
                f"{OLD_PROMPT_CMD} > hook.log",
                f"{PROMPT_CMD} > hook.log",
            ),
            (
                f"echo one | cat && {OLD_PROMPT_CMD}",
                f"echo one | cat && {PROMPT_CMD}",
            ),
        ):
            with self.subTest(command=compound):
                self.write_settings(settings_with(compound))
                proc = self.vendor()
                self.assertEqual(
                    proc.returncode, 0, proc.stdout + proc.stderr
                )
                self.assertEqual(
                    self.commands("UserPromptSubmit"), [want]
                )
                self.settings.unlink()


if __name__ == "__main__":
    unittest.main()
