import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._lib import miniyaml

# Shape mirrors `plan.yaml` in docs/plans/2026-10-03-betterterms-v1.md
# ("Shared interfaces"): scalar fields, a nested map, and lists of maps.
SAMPLE_PLAN = """\
# written by betterterms-plan
target: 70
currency: USD
options:
  - label: annual
    value: 65
    terms: 12-month prepay
  - label: monthly
    value: 80
    terms: cancel anytime
ladder:
  - value: 70
    reason: target
  - value: 85
    reason: fallback if pushed
patience:
  rounds: 3
  days: 14
timing: before renewal
channel: email
facts:
  - id: f1
    text: competitor charges $89 per month
    source: https://example.com/pricing
  - id: f2
    text: "policy allows retention offers"
    source: https://example.com/policy
"""


class LoadTest(unittest.TestCase):
    def test_inline_list(self):
        self.assertEqual(miniyaml.load("a: [1, 2]"), {"a": [1, 2]})

    def test_sample_plan_shape(self):
        plan = miniyaml.load(SAMPLE_PLAN)
        self.assertEqual(plan["target"], 70)
        self.assertEqual(plan["options"][0], {"label": "annual", "value": 65, "terms": "12-month prepay"})
        self.assertEqual(plan["patience"], {"rounds": 3, "days": 14})
        self.assertEqual(plan["facts"][1]["id"], "f2")

    def test_tab_indentation_raises_with_line_number(self):
        with self.assertRaises(miniyaml.Error) as cm:
            miniyaml.load("\ta: 1")
        self.assertIn("line 1", str(cm.exception))

    def test_dollar_amount_stays_string(self):
        out = miniyaml.load('price: "$1,200"')
        self.assertEqual(out, {"price": "$1,200"})
        self.assertIsInstance(out["price"], str)

    def test_scalar_types(self):
        out = miniyaml.load("i: 3\nf: 1.5\nb: true\nn: null\ns: hello\n")
        self.assertEqual(out, {"i": 3, "f": 1.5, "b": True, "n": None, "s": "hello"})

    def test_block_scalar(self):
        out = miniyaml.load("text: |\n  first line\n  second line\nnext: 1\n")
        self.assertEqual(out["text"], "first line\nsecond line\n")
        self.assertEqual(out["next"], 1)

    def test_missing_colon_raises(self):
        with self.assertRaises(miniyaml.Error):
            miniyaml.load("a: 1\njust text\n")


class DumpTest(unittest.TestCase):
    def test_round_trip_sample_plan(self):
        plan = miniyaml.load(SAMPLE_PLAN)
        self.assertEqual(miniyaml.load(miniyaml.dump(plan)), plan)

    def test_round_trip_scalars_and_nested(self):
        obj = {
            "a": [1, "two", None, True, 2.5],
            "b": {"c": "x: y", "d": "$1,200", "e": "trailing "},
            "empty_list": [],
            "empty_map": {},
            "multiline": "one\ntwo",
        }
        self.assertEqual(miniyaml.load(miniyaml.dump(obj)), obj)


if __name__ == "__main__":
    unittest.main()
