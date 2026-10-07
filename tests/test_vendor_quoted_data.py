"""vendor-into-repo ownership is shell-quote aware: an owned hook
path that appears only as quoted data -- behind a ``;`` ``&`` ``|``
that sits inside a quoted argument -- is not an invocation. It must
survive byte for byte, must not be rewritten as if it were the old
hook, and must not count as the guarded hook already registered.
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
OLD_HOOK = ".claude/betterterms/hooks/prompt_commands.py"
NEW_HOOK = ".claude/betterterms/hooks/prompt-guard.sh"
OLD_PROMPT_CMD = (
    'python3 "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
    'prompt_commands.py"'
)


def quoted_data(path, interpreter):
    """The reported reproduction: the owned path is data inside a
    single-quoted printf argument, and the ``|`` is quoted too."""
    return (
        "printf '%s' '| "
        + interpreter
        + ' "$CLAUDE_PROJECT_DIR/'
        + path
        + '" data\''
    )


class QuotedSeparatorDataTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = make_repo(self.tmp)
        self.target = self.tmp / "consumer"
        self.target.mkdir()
        self.settings = self.target / ".claude" / "settings.json"

    def entry(self, command):
        return {"hooks": [{"type": "command", "command": command}]}

    def vendor_with(self, *entries):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(
            json.dumps({"hooks": {"UserPromptSubmit": list(entries)}}),
            encoding="utf-8",
        )
        proc = run(self.repo, "vendor-into-repo", str(self.target))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def commands(self, settings):
        return [
            h["command"]
            for entry in settings["hooks"]["UserPromptSubmit"]
            for h in entry["hooks"]
        ]

    def test_old_path_quoted_data_is_never_rewritten(self):
        # The only mention of prompt_commands.py is inside quotes:
        # nothing invokes it, so nothing may be migrated. The entry
        # survives verbatim and the guarded hook still registers.
        data = quoted_data(OLD_HOOK, "python3")
        settings = self.vendor_with(self.entry(data))
        self.assertEqual(self.commands(settings), [data, PROMPT_CMD])

    def test_new_path_quoted_data_is_not_registration(self):
        # A quoted prompt-guard.sh mention is not the hook launch:
        # it must not suppress the real registration.
        data = quoted_data(NEW_HOOK, "bash")
        settings = self.vendor_with(self.entry(data))
        self.assertEqual(self.commands(settings), [data, PROMPT_CMD])

    def test_quoted_data_does_not_shield_a_real_old_hook(self):
        # Quoted prompt-guard data plus a real old invocation: the
        # quoted mention must not count as registered, so the old
        # hook migrates and the data entry is kept byte for byte.
        data = quoted_data(NEW_HOOK, "bash")
        settings = self.vendor_with(
            self.entry(data), self.entry(OLD_PROMPT_CMD)
        )
        self.assertEqual(self.commands(settings), [data, PROMPT_CMD])


if __name__ == "__main__":
    unittest.main()
