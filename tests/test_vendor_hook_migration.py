"""vendor-into-repo migrates the pre-guard prompt_commands.py hook
entry to the guarded prompt-guard.sh launcher. The ownership boundary
is exact: a command string is ours only when it is the vendored launch,
so lookalike names and path-as-argument mentions are never rewritten
and never suppress the real registration.
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
SESSION_CMD = (
    'bash "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
    'session-start.sh"'
)


class VendorMigrationTest(unittest.TestCase):
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

    def read(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def commands(self, event):
        """The command strings registered under ``hooks.<event>``."""
        return [
            h["command"]
            for entry in self.read()["hooks"][event]
            for h in entry["hooks"]
        ]

    def test_old_owned_prompt_hook_migrates_to_the_guard(self):
        # A settings file from the pre-guard vendor run: the owned
        # prompt_commands.py command is rewired to the guarded
        # launcher in place, with the entry's other fields kept and
        # no duplicate entry added.
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "matcher": "kept",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": OLD_PROMPT_CMD,
                                        "timeout": 30,
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        settings = self.read()
        entries = settings["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["matcher"], "kept")
        hooks = entries[0]["hooks"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["command"], PROMPT_CMD)
        self.assertEqual(hooks[0]["timeout"], 30)

    def test_migration_is_idempotent(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": OLD_PROMPT_CMD,
                                    }
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        for _ in range(2):
            proc = self.vendor()
            self.assertEqual(
                proc.returncode, 0, proc.stdout + proc.stderr
            )
        self.assertEqual(self.commands("UserPromptSubmit"), [PROMPT_CMD])

    def test_similarly_named_custom_hook_is_untouched(self):
        # A hook whose name merely shares the prompt_ prefix is not
        # ours: it must not be migrated or silently suppress the
        # real registration.
        custom = (
            'bash "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
            'prompt-linter.sh"'
        )
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": custom,
                                    },
                                    {
                                        "type": "command",
                                        "command": OLD_PROMPT_CMD,
                                    },
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        commands = self.commands("UserPromptSubmit")
        self.assertEqual(
            sorted(commands), sorted([custom, PROMPT_CMD])
        )

    def test_guarded_hook_present_drops_old_owned_copy(self):
        # Both shapes registered: the unguarded copy must not keep
        # running, and the guarded one stays exactly once.
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": OLD_PROMPT_CMD,
                                    },
                                    {
                                        "type": "command",
                                        "command": PROMPT_CMD,
                                    },
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.commands("UserPromptSubmit"), [PROMPT_CMD])

    def test_suffixed_owned_names_are_not_ours(self):
        # prompt_commands.py-custom and prompt-guard.sh-custom are
        # different files: the old-suffix hook must survive and must
        # not stop a fresh guarded registration, and the new-suffix
        # hook must not count as the guarded one already present.
        old_custom = (
            'python3 "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
            'prompt_commands.py-custom"'
        )
        new_custom = (
            'bash "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
            'prompt-guard.sh-custom"'
        )
        for custom in (old_custom, new_custom):
            with self.subTest(custom=custom):
                self.settings.parent.mkdir(parents=True, exist_ok=True)
                self.settings.write_text(
                    json.dumps(
                        {
                            "hooks": {
                                "UserPromptSubmit": [
                                    {
                                        "hooks": [
                                            {
                                                "type": "command",
                                                "command": custom,
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                proc = self.vendor()
                self.assertEqual(
                    proc.returncode, 0, proc.stdout + proc.stderr
                )
                self.assertEqual(
                    sorted(self.commands("UserPromptSubmit")),
                    sorted([custom, PROMPT_CMD]),
                )
                self.settings.unlink()

    def test_path_as_data_is_never_rewritten(self):
        # A command that merely mentions the owned path as an
        # argument is not the hook launch and must not be edited.
        data = (
            'cp "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
            'prompt_commands.py" /tmp/x'
        )
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {"hooks": [{"type": "command", "command": data}]}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        commands = self.commands("UserPromptSubmit")
        self.assertIn(data, commands)
        self.assertIn(PROMPT_CMD, commands)

    def test_commented_out_owned_invocation_is_not_active(self):
        # An owned path inside a shell comment was never invoked:
        # ``#`` at a word start comments the rest of the line, so a
        # mention there is data, not registration. It must neither
        # suppress installing the real guarded hook nor be rewritten
        # -- the comment command survives byte-exact, exactly one
        # real guard invocation is added, and a re-run is a no-op.
        for commented in (
            "echo setup # ; " + OLD_PROMPT_CMD,
            "echo setup # ; " + PROMPT_CMD,
        ):
            with self.subTest(command=commented):
                self.settings.parent.mkdir(parents=True, exist_ok=True)
                self.settings.write_text(
                    json.dumps(
                        {
                            "hooks": {
                                "UserPromptSubmit": [
                                    {
                                        "hooks": [
                                            {
                                                "type": "command",
                                                "command": commented,
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                proc = self.vendor()
                self.assertEqual(
                    proc.returncode, 0, proc.stdout + proc.stderr
                )
                self.assertEqual(
                    self.commands("UserPromptSubmit"),
                    [commented, PROMPT_CMD],
                )
                first = self.settings.read_text(encoding="utf-8")
                proc = self.vendor()
                self.assertEqual(
                    proc.returncode, 0, proc.stdout + proc.stderr
                )
                self.assertEqual(
                    self.settings.read_text(encoding="utf-8"), first
                )
                self.settings.unlink()

    def test_commented_guard_mention_does_not_suppress_migration(self):
        # A commented-out mention of the guarded path is not an
        # installed guard: the real old invocation still migrates to
        # the guard (not ``true``), and the comment stays verbatim.
        commented = "echo setup # ; " + PROMPT_CMD
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": commented,
                                    },
                                    {
                                        "type": "command",
                                        "command": OLD_PROMPT_CMD,
                                    },
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(
            self.commands("UserPromptSubmit"), [commented, PROMPT_CMD]
        )

    def test_commented_session_start_path_is_not_registered(self):
        # The same ownership boundary applies to SessionStart: a
        # commented-out session-start.sh mention does not count as
        # installed, so the real entry is added and the comment is
        # left alone.
        commented = "echo setup # ; " + SESSION_CMD
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "matcher": "startup",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": commented,
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        commands = self.commands("SessionStart")
        self.assertIn(commented, commands)
        self.assertIn(SESSION_CMD, commands)


if __name__ == "__main__":
    unittest.main()
