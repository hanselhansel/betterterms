import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "betterterms-guardrails" / "scripts"))

from btlib import money


class AmountsTest(unittest.TestCase):
    def test_dollar_commas(self):
        self.assertEqual(money.amounts("$1,200"), [1200.0])

    def test_decimal(self):
        self.assertEqual(money.amounts("1200.00"), [1200.0])

    def test_k_suffix(self):
        self.assertEqual(money.amounts("1.2k"), [1200.0])

    def test_currency_code(self):
        self.assertEqual(money.amounts("USD 1200"), [1200.0])

    def test_currency_symbol_code(self):
        self.assertEqual(money.amounts("S$1,200"), [1200.0])

    def test_spelled_hundreds(self):
        self.assertEqual(money.amounts("twelve hundred"), [1200.0])

    def test_spelled_thousands(self):
        self.assertIn(1200.0, money.amounts("one thousand two hundred"))

    def test_spelled_millions(self):
        self.assertIn(2000000.0, money.amounts("two million"))

    def test_spelled_with_currency_word(self):
        self.assertIn(350000.0, money.amounts("three hundred fifty thousand dollars"))

    def test_dollars_suffix(self):
        self.assertEqual(money.amounts("1200 dollars"), [1200.0])

    def test_fact_id_is_not_an_amount(self):
        self.assertEqual(money.amounts("claim f9 is wrong"), [])

    def test_no_amounts(self):
        self.assertEqual(money.amounts("see you next week"), [])

    def test_currency_marked_flag(self):
        marked = {a.value for a in money.find("pay $1,200 over 3 years") if a.marked}
        self.assertEqual(marked, {1200.0})

    def test_bare_number_unmarked(self):
        found = money.find("I have 3 options")
        self.assertTrue(any(a.value == 3.0 and not a.marked for a in found))


if __name__ == "__main__":
    unittest.main()
