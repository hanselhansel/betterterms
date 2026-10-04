"""User-facing doc checks outside scripts/verify: the command path a
user is told to run must be absolute (``bt.py where`` resolves it at
run time), and VERSION pins the release.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUIDES = REPO / "docs" / "guides"
INTAKE = REPO / "skills" / "betterterms-intake" / "SKILL.md"

# Written split so this file's own text never matches the pattern.
REL_BT = re.compile(r"\.\.[/\\]" + r"\S*bt\.py")


class UserDocsTest(unittest.TestCase):
    def test_no_relative_bt_paths_in_user_docs(self):
        """``python3 ../betterterms-guardrails/scripts/bt.py`` only
        resolves inside the skill tree, so it may never appear in a
        guide, and in intake it may only appear on the ``bt.py where``
        line that resolves the absolute path the user sees."""
        hits = []
        for path in sorted(GUIDES.glob("*.md")):
            rel = path.relative_to(REPO)
            for n, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if REL_BT.search(line):
                    hits.append(f"{rel}:{n}")
        for n, line in enumerate(
            INTAKE.read_text(encoding="utf-8").splitlines(), 1
        ):
            if REL_BT.search(line) and "where" not in line:
                hits.append(f"{INTAKE.relative_to(REPO)}:{n}")
        self.assertEqual(hits, [])

    def test_version_is_0_10_0(self):
        self.assertEqual(
            (REPO / "VERSION").read_text(encoding="utf-8").strip(),
            "0.10.0",
        )


if __name__ == "__main__":
    unittest.main()
