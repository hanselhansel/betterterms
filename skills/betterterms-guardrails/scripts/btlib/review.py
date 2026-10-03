"""The review-tier text scan: an allowlist, not a blacklist.

``review(find, floor, never_items)`` reads ``find.masked`` (each
non-fact placeholder output replaced by :data:`render._MASK`, fact
text visible) and returns one plain-word reason per tripped check;
reasons carry no numbers. Every character must be on the allowed
set and every alphanumeric token must be clean (decision 0009
amendment). Anything unusual routes to the user: off-allowlist
characters, a sentinel the template or a fact itself carried,
tokens mixing letters and digits, disallowed numbers, listed money
and commitment words, and sentinel glue.
"""

import re

from . import FLOOR_TOL, money, render, wordlists

# The review-tier allowlist: ASCII letters and digits, space and
# newline, this punctuation set and the sentinel. Any other character
# (non-ASCII letters, homoglyphs, controls, format, combining and
# other private-use characters, currency signs, symbols) routes to
# the user, which is why non-English text always needs approval.
_ALLOWED = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    " \n.,;:!?'\"()-/&" + render._MASK
)
# Free text splits into alphanumeric runs: one linear pass, no
# backtracking.
_TOKEN = re.compile(r"[0-9A-Za-z]+")


def _touching(text):
    """Characters that could extend a rendered amount sit right
    against a mask sentinel. Returns the kinds found: ``digit`` for a
    digit directly on the sentinel ("$1,100" plus "0" restates the
    price), ``letter`` for a letter ("$1,100k" reads as 1,100,000) and
    ``decimal`` for a ``.``/``,`` separator with a digit on its far
    side ("$1,100.99"). An empty set means the sentinel is clean."""
    found = set()
    for i, c in enumerate(text):
        if c != render._MASK:
            continue
        for j in (i - 1, i + 1):
            if not 0 <= j < len(text):
                continue
            d = text[j]
            if d.isascii() and d.isdigit():
                found.add("digit")
            elif d.isascii() and d.isalpha():
                found.add("letter")
            elif d in ".,":
                k = j + (j - i)  # the character past the separator
                if (0 <= k < len(text) and text[k].isascii()
                        and text[k].isdigit()):
                    found.add("decimal")
    return found


def _tokens(text):
    """All alphanumeric tokens of ``text`` as ``(start, end, token)``
    in order: one linear pass, no backtracking."""
    return [(m.start(), m.end(), m.group(0)) for m in _TOKEN.finditer(text)]


def _is_year(masked, toks, i):
    """A 1900-2100 digit token is a year only when it follows a
    whole-word month name ("Jan 2026", "15 October 2026") or a month,
    a day 1-31 and a comma ("October 15, 2026")."""
    tok = toks[i][2]
    if len(tok) != 4 or not 1900 <= int(tok) <= 2100 or i == 0:
        return False
    if toks[i - 1][2].lower() in wordlists.MONTH_WORDS:
        return True
    if (
        i >= 2
        and toks[i - 1][2].isdigit()
        and len(toks[i - 1][2]) <= 3
        and 1 <= int(toks[i - 1][2]) <= 31
        and toks[i - 2][2].lower() in wordlists.MONTH_WORDS
    ):
        gap = masked[toks[i - 1][1]:toks[i][0]]
        return "," in gap and all(c in ", \t\n" for c in gap)
    return False


def _small_number(digits):
    """A standalone digit run passes only as a small count: no leading
    zero, one or two digits, value 1-99."""
    return len(digits) <= 2 and not digits.startswith("0")


def _joins(gap, nxt):
    """Whether ``gap`` between two digit tokens fuses them into one
    number. Pure whitespace joins any width ("1 050", "12 50"); a gap
    holding a "," or "." joins only a three-digit tail, the grouped
    thousands shape ("1,050", "1.099"). Anything else keeps the two
    tokens separate, so "90.5" and "3.11" stay decimals."""
    if all(c in " \n" for c in gap):
        return True
    return (
        len(nxt) == 3
        and any(c in ",." for c in gap)
        and all(c in ",. \n" for c in gap)
    )


def _digit_groups(masked, toks, years):
    """Fuse consecutive digit tokens into joined numbers so a
    separator-split figure is judged whole, never as separate small
    tokens. A 1900-2100 token after a month name is a year and joins
    nothing. Returns the joined digit strings."""
    groups = []
    i = 0
    while i < len(toks):
        if not toks[i][2].isdigit() or years[i]:
            i += 1
            continue
        digits = toks[i][2]
        while (
            i + 1 < len(toks)
            and toks[i + 1][2].isdigit()
            and not years[i + 1]
            and _joins(masked[toks[i][1]:toks[i + 1][0]], toks[i + 1][2])
        ):
            i += 1
            digits += toks[i][2]
        groups.append(digits)
        i += 1
    return groups


def review(find, floor, never_items):
    """Review-tier checks on the rendered message. Reads ``find.masked``
    (placeholder outputs masked, fact text visible) and returns one
    plain-word reason per tripped check; reasons carry no numbers.
    The scan is an allowlist: characters off the permitted set, a mask
    sentinel that arrived from the template or a fact, tokens that mix
    letters and digits, disallowed numbers, listed money and
    commitment words and sentinel glue all go to the user."""
    reasons = []
    masked = find.masked
    if find.sentinel or any(c not in _ALLOWED for c in masked):
        reasons.append("unusual characters in the message")
    touch = _touching(masked)
    if "digit" in touch:
        reasons.append("a digit next to a rendered amount")
    if touch:
        reasons.append("text touches a rendered amount")
    toks = _tokens(masked)
    lower = [t.lower() for _, _, t in toks]
    for i, (_, _, tok) in enumerate(toks):
        if any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            reasons.append("a token mixing letters and digits in the message")
        l = lower[i]
        if l in wordlists.SCALE_WORDS:
            reasons.append("a scale word in the message")
        if l in wordlists.CURRENCY_WORDS or tok in wordlists.CURRENCY_CODES:
            reasons.append("a currency symbol or code in the message")
        if l in wordlists.COMMIT_WORDS:
            reasons.append("agreement or commitment wording in the message")
        if l == "k" and i > 0 and toks[i - 1][2].isdigit():
            reasons.append("a scale word in the message")
    years = [
        toks[i][2].isdigit() and _is_year(masked, toks, i)
        for i in range(len(toks))
    ]
    groups = _digit_groups(masked, toks, years)
    if any(not _small_number(d) for d in groups):
        reasons.append("a number in the message")
    # Number words adjacent as tokens form one run: the separator
    # between them is never alphanumeric, so punctuation and newlines
    # cannot split it ("eleven\nninety\nnine", "one, two").
    if any(
        lower[i] in wordlists.NUMBER_WORDS
        and lower[i + 1] in wordlists.NUMBER_WORDS
        for i in range(len(toks) - 1)
    ):
        reasons.append("a run of number words in the message")
    if floor is not None and floor < 100:
        # Small integers are harmless except the one that repeats a
        # sub-100 floor's integer part, in digits or as a number word.
        fint = int(floor)
        if (
            any(
                _small_number(d) and int(d) == fint for d in groups
            )
            or any(
                wordlists.NUMBER_WORD_VALUES.get(l) == fint
                for l in lower
            )
        ):
            reasons.append("a number matching your limit")
    for phrase in wordlists.COMMIT_PHRASES:
        width = len(phrase)
        if any(
            lower[i:i + width] == list(phrase)
            for i in range(len(toks) - width + 1)
        ):
            reasons.append("agreement or commitment wording in the message")
            break

    norm = render.normalize(masked)
    low = norm.lower()
    found_amounts = None
    for item in never_items:
        s = render.normalize(str(item)).strip().lower()
        if not s:
            continue
        vals = [] if any(c.isalpha() for c in s) else money.amounts(s)
        if vals:
            # Numeric items match as whole numbers only.
            if found_amounts is None:
                found_amounts = money.amounts(norm)
            hit = any(
                abs(v - a) <= FLOOR_TOL for v in vals for a in found_amounts
            )
        else:
            hit = s in low
        if hit:
            reasons.append("a term from your never-disclose list")
            break
    return reasons
