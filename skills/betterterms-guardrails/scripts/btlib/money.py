"""Money amount extraction for the gate and scorer.

``amounts(text)`` returns every numeric amount mentioned: currency-marked
(``$1,200``, ``USD 1200``, ``S$1,200``, ``1200 dollars``), suffixed
(``1.2k``, ``5m``), bare numbers (``1200.00``) and spelled-out numbers up
to the billions (``twelve hundred``, ``one thousand two hundred``,
``two million``).

``find(text)`` returns :class:`Amount` records with a ``marked`` flag.
Marked means the amount looked like money (currency prefix or suffix,
k/m/b multiplier, or a spelled phrase followed by "dollars"/"bucks").
The gate's untraced-number rule checks marked amounts only; floor-leak
detection compares every amount found.
"""

import re
from collections import namedtuple

Amount = namedtuple("Amount", ["start", "end", "value", "marked"])

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CODES = r"USD|EUR|GBP|JPY|CHF|SGD|AUD|CAD|HKD|NZD|INR|ZAR|SEK|NOK|DKK"
_PREFIX = rf"(?:[A-Za-z]{{1,3}}\$|[$€£₹¥]|{_CODES})\s*"
_SUFFIX = rf"(?:{_CODES}|dollars?|bucks|quid)\b"
_MULT = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9}

_MARKED = re.compile(
    rf"(?<![\w.]){_PREFIX}(?P<num>{_NUM})(?P<mult>k|m|b|bn)?\b(?:\s*{_SUFFIX})?",
    re.IGNORECASE,
)
_SUFFIXED = re.compile(
    rf"(?<![\w.])(?P<num>{_NUM})(?P<mult>k|m|b|bn)\b(?:\s*{_SUFFIX})?"
    rf"|(?<![\w.])(?P<num2>{_NUM})\s*{_SUFFIX}",
    re.IGNORECASE,
)
_DIGIT_SCALE = re.compile(
    rf"(?<![\w.])(?P<num>{_NUM})\s*(?P<scale>thousand|million|billion)\b",
    re.IGNORECASE,
)
_BARE = re.compile(rf"(?<![\w.,])(?:{_NUM})(?![\w])")

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 10**6, "billion": 10**9}
_WORD = "|".join(sorted(set(_UNITS) | set(_TENS) | set(_SCALES) | {"a", "an", "and"}, key=len, reverse=True))
_SPELLED = re.compile(rf"\b(?:{_WORD})(?:[\s-]+(?:{_WORD}))*", re.IGNORECASE)
_AFTER_CURRENCY_WORD = re.compile(rf"\s*{_SUFFIX}", re.IGNORECASE)
_BEFORE_CURRENCY_SIGN = re.compile(r"[$€£₹¥]\s*$")


def _to_num(text):
    return float(text.replace(",", ""))


def _mult_of(group):
    return _MULT[group.lower()] if group else 1.0


def _inside(start, end, spans):
    return any(s <= start and end <= e for s, e, *_ in spans)


def _spelled_value(words):
    """Parse a list of lowercase number words. Returns an int."""
    total = current = 0
    for w in words:
        if w in ("a", "an"):
            current += 1
        elif w == "and":
            continue
        elif w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        else:
            total += (current or 1) * _SCALES[w]
            current = 0
    return total + current


def _spelled_words(text):
    words = [w for w in re.split(r"[\s-]+", text.lower()) if w]
    while words and words[0] == "and":
        words.pop(0)
    while words and words[-1] == "and":
        words.pop()
    if not words or all(w in ("a", "an") for w in words):
        return None
    return words


def find(text):
    """Return all amounts in ``text`` as Amount(start, end, value, marked)."""
    spans = []
    for m in _MARKED.finditer(text):
        value = _to_num(m.group("num")) * _mult_of(m.group("mult"))
        spans.append(Amount(m.start(), m.end(), value, True))
    for m in _SUFFIXED.finditer(text):
        if _inside(m.start(), m.end(), spans):
            continue
        num = m.group("num") or m.group("num2")
        spans.append(Amount(m.start(), m.end(), _to_num(num) * _mult_of(m.group("mult")), True))
    for m in _DIGIT_SCALE.finditer(text):
        if _inside(m.start(), m.end(), spans):
            continue
        value = _to_num(m.group("num")) * _SCALES[m.group("scale").lower()]
        marked = bool(_AFTER_CURRENCY_WORD.match(text[m.end():])) or bool(
            _BEFORE_CURRENCY_SIGN.search(text[: m.start()])
        )
        spans.append(Amount(m.start(), m.end(), value, marked))
    for m in _SPELLED.finditer(text):
        if _inside(m.start(), m.end(), spans):
            continue
        words = _spelled_words(m.group(0))
        if words is None:
            continue
        marked = bool(_AFTER_CURRENCY_WORD.match(text[m.end():])) or bool(
            _BEFORE_CURRENCY_SIGN.search(text[: m.start()])
        )
        spans.append(Amount(m.start(), m.end(), float(_spelled_value(words)), marked))
    for m in _BARE.finditer(text):
        if _inside(m.start(), m.end(), spans):
            continue
        spans.append(Amount(m.start(), m.end(), _to_num(m.group(0)), False))
    spans.sort(key=lambda a: a.start)
    return spans


def amounts(text):
    """Return the numeric values of every amount found in ``text``."""
    return [a.value for a in find(text)]
