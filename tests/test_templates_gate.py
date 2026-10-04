"""The shipped-template self-check: every fenced block in
skills/*/references/templates/*.md renders against the fixture case
and passes the gate at autonomy 3 and 4, so a template can never
ship wording the gate itself would stop. ``<slot>`` markers are
agent fill-ins: the check substitutes a stand-in before gating.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from _lib.checks_templates import check_templates_gate, gate_template  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "template_case"


class ShippedTemplatesGateTest(unittest.TestCase):
    def test_templates_gate_passes_all_shipped(self):
        ok, detail = check_templates_gate(REPO)
        self.assertTrue(ok, detail)

    def test_negated_commit_phrase_passes_review(self):
        # "no longer works for me" is a decline, not a commitment:
        # a fixture template containing it passes review at
        # autonomy 3 and 4.
        verdicts = gate_template(
            "The current price no longer works for me.", FIXTURE
        )
        for autonomy, result, reasons in verdicts:
            with self.subTest(autonomy=autonomy):
                self.assertEqual(result, "pass", reasons)

    def test_unnegated_commit_phrase_still_routes(self):
        # Control: the bare phrase stays a review hit, proving the
        # check really runs the gate.
        verdicts = gate_template("That works for me.", FIXTURE)
        for _autonomy, result, _reasons in verdicts:
            self.assertEqual(result, "needs_approval")


if __name__ == "__main__":
    unittest.main()
