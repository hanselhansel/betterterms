"""Money amount extraction for the scorer and inbound parsing.

``amounts(text)`` returns every numeric amount mentioned: currency-marked
(``$1,200``, ``USD 1200``, ``S$1,200``, ``1200 dollars``, ``1200 EUR``),
suffixed (``1.2k``, ``5m``, ``5mm``, ``2bn``, ``1.2 grand``), digits plus
a scale word (``1.5 thousand``, ``12 hundred``, ``$1.2 million``),
space-grouped thousands (``1 200``), hedged forms (``~1200``,
``1200ish``, ``1,200-ish``), per-period forms (``1200/mo``, ``1200 a
month``), bare numbers (``1200.00``) and spelled-out numbers up to the
billions (``twelve hundred``, ``one thousand, two hundred``,
``two million``).

``find(text)`` returns :class:`Amount` records (start, end, value).
The scorer's suggested-amounts listing and inbound amount extraction
read these results. Decision 0010: the gate never parses free text
for floor rules, so nothing on the gate path imports this module.

Parsed values saturate at ``_CAP``: a hostile digit run or spelled
phrase returns the cap instead of raising OverflowError or yielding
infinity. Only the first ``MAX_TEXT`` characters are scanned, so a
huge input costs the same as a 64 KB one. Every pattern is
linear-time: no nested quantifiers, fixed-lookbehind anchors.
Overlap suppression merges each pass's spans once, so the whole scan
stays linear on hostile input.
"""

import bisect
import re
from collections import namedtuple
from heapq import merge

from . import MAX_TEXT, wordlists

Amount = namedtuple("Amount", ["start", "end", "value"])

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SPACE_NUM = r"\d{1,3}(?: \d{3})+"
# The shared ISO-style code list; the review tier matches the same set
# case-sensitively while these patterns match case-insensitively.
_CODES = "|".join(
    sorted(wordlists.CURRENCY_CODES, key=len, reverse=True)
)
_PREFIX = rf"(?:[A-Za-z]{{1,3}}\$|[$€£₹¥]|{_CODES})\s*"
_SUFFIX = rf"(?:{_CODES}|dollars?|bucks|quid)\b"
_PERIOD = r"(?:mo|month|yr|year|week|wk|day|hr|hour|annum|quarter)s?\b"

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
# Multipliers after a number: the scale words plus the compact suffixes,
# so "5mm", "2bn", "1.2 grand" and "$1.2 million" all scale the number
# they follow.
_MULT = {**_SCALES, "k": 1e3, "m": 1e6, "mm": 1e6, "b": 1e9, "bn": 1e9,
         "grand": 1e3}
_MULT_RE = "|".join(sorted(_MULT, key=len, reverse=True))
_SCALE_RE = "|".join(sorted(_SCALES, key=len, reverse=True))
_SCALE_WORD_VALUE = {**_SCALES, "grand": 1e3}

# A currency-marked number may carry a multiplier after it: "$1.2
# million" is one marked 1,200,000, never a stray 1.2 next to a million.
# Every lookbehind also excludes ",": without it each position after a
# comma in a ",123,123,..." run passes the anchor, and _NUM then walks
# the whole tail, which is quadratic on a comma-digit run.
_MARKED = re.compile(
    rf"(?<![\w.,]){_PREFIX}(?P<num>{_NUM})(?:\s*(?P<mult>{_MULT_RE}))?\b"
    rf"(?:\s*{_SUFFIX})?",
    re.IGNORECASE,
)
_SUFFIXED = re.compile(
    rf"(?<![\w.,])(?P<num>{_NUM})(?P<mult>{_MULT_RE})\b(?:\s*{_SUFFIX})?"
    rf"|(?<![\w.,])(?P<num2>{_NUM})\s*{_SUFFIX}",
    re.IGNORECASE,
)
# A digit plus a scale word is a marked amount: "12 hundred", "1.5
# thousand" and "1.2 grand" all state money. Compact letters (k, m) need
# adjacency and live in _SUFFIXED; a spaced "m" is more likely meters.
_SCALE_WORD = re.compile(
    rf"(?<![\w.,])(?P<num>{_NUM})\s*(?P<scale>{_SCALE_RE}|grand)\b",
    re.IGNORECASE,
)
# Hedged or approximate forms are still marked amounts: "1200ish" and
# "~1200" state a number just as surely as "$1200". The whitespace
# around the dash is bounded, so a long run of spaces cannot feed the
# matcher a quadratic walk.
_ISH = re.compile(
    rf"(?<![\w.,])(?P<num>{_NUM})\s{{0,20}}-?\s{{0,20}}ish\b",
    re.IGNORECASE,
)
_APPROX = re.compile(rf"(?<![\w.,])(?:~|≈)\s*(?P<num>{_NUM})")
_PER = re.compile(
    rf"(?<![\w.,])(?P<num>{_NUM})"
    rf"(?:\s*/\s*|\s+(?:a|an|per|each|every)\s+){_PERIOD}",
    re.IGNORECASE,
)
# Space-grouped thousands ("1 200", "1 234 567") mark money the same way
# commas do. A run that is not groups of three stays bare.
_SPACE_GROUP = re.compile(rf"(?<![\w.,])(?P<num>{_SPACE_NUM})(?![\w.])")
_BARE = re.compile(rf"(?<![\w.,])(?:{_NUM})(?![\w])")
_WORD = "|".join(sorted(set(_UNITS) | set(_TENS) | set(_SCALES) | {"a", "an", "and"}, key=len, reverse=True))
# Commas join spelled phrases ("one thousand, two hundred") the same way
# spaces do.
_SPELLED = re.compile(rf"\b(?:{_WORD})(?:[\s,-]+(?:{_WORD}))*", re.IGNORECASE)

# Parsed values clamp here: no result is ever inf or an OverflowError.
_CAP = 1e18
_CAP_INT = 10**18


def _clamp(value):
    return value if value <= _CAP else _CAP


def _to_num(text):
    return _clamp(float(text.replace(",", "").replace(" ", "")))


def _mult_of(group):
    return _MULT[group.lower()] if group else 1.0


def _covered(taken, start, end):
    """True when ``taken`` (sorted, disjoint spans) overlaps [start, end).
    Binary search plus a neighbour check keeps this O(log n)."""
    i = bisect.bisect_left(taken, (start, -1))
    if i < len(taken) and taken[i][0] < end:
        return True
    return i > 0 and taken[i - 1][1] > start


def _spelled_value(words):
    """Parse a list of lowercase number words. Returns an int bounded
    by ``_CAP_INT`` so ``float()`` can never overflow: "hundred" x 155
    saturates instead of building a 300-digit int."""
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
            current = min((current or 1) * 100, _CAP_INT)
        else:
            total = min(total + (current or 1) * _SCALES[w], _CAP_INT)
            current = 0
    return min(total + current, _CAP_INT)


def _spelled_words(text):
    words = [w for w in re.split(r"[\s,-]+", text.lower()) if w]
    while words and words[0] == "and":
        words.pop(0)
    while words and words[-1] == "and":
        words.pop()
    if not words or all(w in ("a", "an") for w in words):
        return None
    return words


def find(text):
    """Return all amounts in ``text`` as Amount(start, end, value)."""
    found = []
    taken = []
    text = text[:MAX_TEXT]

    def scan(regex, parse):
        added = []
        for m in regex.finditer(text):
            hit = parse(m)
            if hit is None or _covered(taken, m.start(), m.end()):
                continue
            added.append(m.span())
            found.append(Amount(m.start(), m.end(), hit))
        # Matches arrive sorted within a pass; one linear merge keeps the
        # whole scan linear instead of a per-match list insert.
        if added:
            taken[:] = list(merge(taken, added))

    def scaled(m):
        g = m.groupdict()
        num = g.get("num") or g.get("num2")
        return _clamp(_to_num(num) * _mult_of(g.get("mult")))

    def spelled(m):
        words = _spelled_words(m.group(0))
        if words is None:
            return None
        return float(_spelled_value(words))

    scan(_MARKED, scaled)
    scan(_SUFFIXED, scaled)
    scan(_SCALE_WORD, lambda m: _clamp(_to_num(m.group("num")) * _SCALE_WORD_VALUE[m.group("scale").lower()]))
    scan(_ISH, lambda m: _to_num(m.group("num")))
    scan(_APPROX, lambda m: _to_num(m.group("num")))
    scan(_PER, lambda m: _to_num(m.group("num")))
    scan(_SPACE_GROUP, lambda m: _to_num(m.group("num")))
    scan(_SPELLED, spelled)
    scan(_BARE, lambda m: _to_num(m.group(0)))
    found.sort(key=lambda a: a.start)
    return found


def amounts(text):
    """Return the numeric values of every amount found in ``text``."""
    return [a.value for a in find(text)]
