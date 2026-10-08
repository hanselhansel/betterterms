"""The mod's draftYaml() output must load through the gate's real
YAML parser (btlib.yaml = vendored PyYAML), not just the mod's own
mini reader. The literal block's explicit indent indicator is what
keeps a template whose first content line is indented, or whose
leading lines are blank, byte-exact after a held-draft edit
round-trip.
"""

import json
import subprocess
import unittest
import sys
from pathlib import Path

from bt_helpers import REPO
from btlib import yaml

MOD = REPO / "mod" / "lib" / "approvals.js"

EMIT = (
    "const A = await import(process.argv[1]);"
    "const held = JSON.parse(process.argv[2]);"
    "process.stdout.write(A.draftYaml(held, JSON.parse(process.argv[3])));"
)

HELD = {
    "action": "send",
    "offer": 1200,
    "period": "month",
    "currency": "USD",
    "claims": ["counterparty claims it is the best rate"],
}


def draft_yaml(text):
    proc = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            EMIT,
            str(MOD),
            json.dumps(HELD),
            json.dumps(text),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node emit failed: {proc.stderr}")
    return proc.stdout


@unittest.skipUnless(MOD.exists(), "mod sources not vendored here")
class DraftYamlRoundTripTest(unittest.TestCase):
    """Every template shape a user could type must survive the real
    loader: blank-first-line templates are the case the old
    first-character sniff lost."""

    def round_trip(self, text):
        loaded = yaml.load(draft_yaml(text))
        self.assertEqual(loaded["template"], text)
        # The held tuple survives the round-trip; claims are never
        # carried into the editable draft.
        self.assertEqual(loaded["action"], "send")
        self.assertEqual(loaded["offer"], 1200)
        self.assertEqual(loaded["period"], "month")
        self.assertNotIn("claims", loaded)
        return loaded

    def test_plain_text(self):
        self.round_trip("plain one-line")

    def test_leading_blank_line_then_indented_line(self):
        self.round_trip("\n  indented line after a leading blank")

    def test_leading_blank_line_then_tab(self):
        self.round_trip("\n\tindented after a blank, with a tab")

    def test_leading_spaces_on_first_line(self):
        self.round_trip("  first line leads with two spaces")

    def test_multiple_leading_blank_lines(self):
        self.round_trip("\n\nstarts after two blank lines")

    def test_all_blank_lines(self):
        self.round_trip("\n\n")
        self.round_trip("   \n\t\n ")

    def test_interior_blank_lines(self):
        self.round_trip("line one\n\nline three after a blank")

    def test_trailing_newlines(self):
        self.round_trip("trailing newline\n")
        self.round_trip("two trailing\n\n")

    def test_empty_string(self):
        self.round_trip("")

    def test_yaml_sensitive_characters(self):
        self.round_trip("a # hash and 'quotes' and \"doubles\" stay")
        self.round_trip("counterparty said {quote:1} and [list] here")
        self.round_trip("key: value-looking text")
        self.round_trip("- leading dash line\n- another")
        self.round_trip("ends mid-")

    def test_template_placeholder_survives(self):
        self.round_trip("rendered text with {{slot}} placeholder")


if __name__ == "__main__":
    unittest.main()
