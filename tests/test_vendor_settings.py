"""vendor-into-repo vendors the skills and the hook scripts, then
merges the hook entries into .claude/settings.json. Repo-declared
plugins never load in cloud sessions, so the vendored files are what
a session reads; the settings entries carry "$CLAUDE_PROJECT_DIR"
paths and apply in a session with one repository.
"""

import json
import os
import subprocess
import sys
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


class VendorSettingsTest(unittest.TestCase):
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

    def test_creates_skills_hooks_and_settings_when_absent(self):
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        settings = self.read()
        self.assertNotIn("enabledPlugins", settings)
        self.assertNotIn("extraKnownMarketplaces", settings)
        self.assertEqual(self.commands("UserPromptSubmit"), [PROMPT_CMD])
        self.assertEqual(self.commands("SessionStart"), [SESSION_CMD])
        base = self.target / ".claude"
        for rel in (
            "skills/betterterms-guardrails/scripts/bt.py",
            "skills/.betterterms-version",
            "betterterms/hooks/prompt_commands.py",
            "betterterms/hooks/prompt-guard.sh",
            "betterterms/hooks/_btpath.py",
            "betterterms/hooks/_scan.py",
            "betterterms/hooks/session-start.sh",
            "betterterms/.betterterms-version",
        ):
            self.assertTrue((base / rel).is_file(), rel)

    def test_merges_into_existing_settings_keeping_other_keys(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["Bash(python3:*)"]},
                    "model": "sonnet",
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "echo mine",
                                    }
                                ]
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        settings = self.read()
        self.assertEqual(
            settings["permissions"], {"allow": ["Bash(python3:*)"]}
        )
        self.assertEqual(settings["model"], "sonnet")
        self.assertEqual(
            sorted(self.commands("UserPromptSubmit")),
            sorted(["echo mine", PROMPT_CMD]),
        )
        self.assertEqual(self.commands("SessionStart"), [SESSION_CMD])

    def test_hooks_merge_is_idempotent(self):
        for _ in range(2):
            proc = self.vendor()
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        settings = self.read()
        self.assertEqual(
            settings["hooks"]["UserPromptSubmit"],
            self.read()["hooks"]["UserPromptSubmit"],
        )
        self.assertEqual(self.commands("UserPromptSubmit"), [PROMPT_CMD])
        self.assertEqual(self.commands("SessionStart"), [SESSION_CMD])

    def test_same_hook_command_is_never_duplicated(self):
        # An entry already carrying the vendored command counts as
        # registered whatever its other fields, so a differently
        # shaped record is kept verbatim instead of duplicated.
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "matcher": "custom",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": PROMPT_CMD,
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
        self.assertEqual(entries[0]["matcher"], "custom")
        self.assertEqual(entries[0]["hooks"][0]["timeout"], 30)

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

    def test_hooks_key_wrong_shape_exits_2_without_writing(self):
        for bad in ({"hooks": []}, {"hooks": {"SessionStart": "x"}}):
            with self.subTest(bad=bad):
                self.settings.parent.mkdir(parents=True, exist_ok=True)
                before = json.dumps(bad)
                self.settings.write_text(before, encoding="utf-8")
                proc = self.vendor()
                self.assertEqual(
                    proc.returncode, 2, proc.stdout + proc.stderr
                )
                self.assertEqual(self.settings.read_text(), before)
                self.assertFalse(
                    (self.target / ".claude" / "skills").exists()
                )
                self.assertFalse(
                    (self.target / ".claude" / "betterterms").exists()
                )
                self.settings.unlink()

    def test_invalid_settings_json_exits_2_without_writing(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        proc = self.vendor()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(self.settings.read_text(), "{ not json")
        self.assertFalse((self.target / ".claude" / "skills").exists())
        self.assertFalse(
            (self.target / ".claude" / "betterterms").exists()
        )

    def test_no_hooks_vendors_skills_only(self):
        proc = self.vendor("--no-hooks")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.settings.exists())
        self.assertFalse(
            (self.target / ".claude" / "betterterms").exists()
        )
        self.assertTrue(
            (
                self.target / ".claude/skills/betterterms-start/SKILL.md"
            ).is_file()
        )

    def test_no_hooks_ignores_invalid_settings(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        proc = self.vendor("--no-hooks")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.settings.read_text(), "{ not json")

    def test_enabled_plugins_leftover_gets_a_note(self):
        # A settings file written by the old vendor run still enables
        # the plugin: it never loads in cloud sessions and would load
        # the skills twice locally, so the script says so. The key is
        # kept; removing it is the user's call.
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {"enabledPlugins": {"betterterms@betterterms": True}}
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("enabledPlugins", proc.stdout)
        self.assertIs(
            self.read()["enabledPlugins"]["betterterms@betterterms"],
            True,
        )


class VendoredHookEndToEndTest(unittest.TestCase):
    """The vendored prompt_commands.py runs from the vendored path and
    resolves the vendored bt.py with no CLAUDE_PLUGIN_ROOT."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = make_repo(self.tmp)
        self.target = self.tmp / "consumer"
        self.target.mkdir()
        self.home = self.tmp / "bthome"

    def test_vendored_hook_blocks_floor_and_saves_it(self):
        proc = run(
            self.repo, "vendor-into-repo", str(self.target)
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        hook = (
            self.target
            / ".claude/betterterms/hooks/prompt_commands.py"
        )
        self.assertTrue(hook.is_file())
        case = self.home / "cases" / "case-1"
        case.mkdir(parents=True)
        # Leave no other runtime reachable: the repo copy's bt.py
        # moves aside, so a hook that resolved anywhere but the
        # vendored .claude/skills copy could not write the floor.
        bt_src = (
            self.repo
            / "skills/betterterms-guardrails/scripts/bt.py"
        )
        bt_src.rename(bt_src.with_suffix(".off"))
        env = dict(
            os.environ,
            BETTERTERMS_HOME=str(self.home),
            CLAUDE_PROJECT_DIR=str(self.target),
        )
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        event = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s-1",
            "transcript_path": "/tmp/bt-e2e/transcript.jsonl",
            "cwd": str(self.target),
            "prompt": "bt floor case-1 62",
        }
        proc = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("walk-away saved", out["reason"])
        self.assertNotIn("62", proc.stdout)
        self.assertEqual(
            (case / ".floor").read_text().strip(), "62.00"
        )


if __name__ == "__main__":
    unittest.main()
