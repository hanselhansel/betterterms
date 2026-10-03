import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._lib import frontmatter

SKILL = """\
---
name: betterterms-x
description: Does a thing. Use when the user asks for the thing.
---
Body starts here.
Second line.
"""


class ParseTest(unittest.TestCase):
    def _write(self, text):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        tmp.write(text)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_parses_name_description_and_body(self):
        fm, body = frontmatter.parse(self._write(SKILL))
        self.assertEqual(fm["name"], "betterterms-x")
        self.assertEqual(fm["description"], "Does a thing. Use when the user asks for the thing.")
        self.assertEqual(body, "Body starts here.\nSecond line.\n")

    def test_missing_closing_marker_raises(self):
        path = self._write("---\nname: x\ndescription: never closed\n")
        with self.assertRaises(frontmatter.Error):
            frontmatter.parse(path)

    def test_no_frontmatter_returns_empty_dict(self):
        fm, body = frontmatter.parse(self._write("plain markdown\n"))
        self.assertEqual(fm, {})
        self.assertEqual(body, "plain markdown\n")


if __name__ == "__main__":
    unittest.main()
