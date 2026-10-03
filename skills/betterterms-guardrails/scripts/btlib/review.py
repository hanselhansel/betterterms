"""The review-tier text scan: an allowlist, not a blacklist.

``review(find, floor, never_items)`` reads ``find.masked`` (each
non-fact placeholder output replaced by :data:`render._MASK`, fact
text visible) and ``find.fact_texts``, and returns one plain-word
reason per tripped check; reasons carry no numbers. Decision 0010
keeps the tier simple and strict: any spelled number word or scale
abbreviation, any decimal or separator-joined digit form, any digit
token that is not isolated, any currency word, code or symbol, and
any fact whose text states a number its ``amount`` does not carry
routes to the user. Only isolated 1-2 digit integers (1-99, no
leading zero) and whole-word month-name dates pass. The character
allowlist, the sentinel rules and the commitment-word rules are
unchanged from the 0009 amendment.
"""

import re

from . import FLOOR_TOL, cases, render, wordlists

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
_SEP = ",. \n"


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
    """A standalone digit token passes only as a small count: no
    leading zero, one or two digits, value 1-99."""
    return len(digits) <= 2 and not digits.startswith("0")


def _moneyish(tok):
    """Whether a token is number-shaped for the isolation rule: a
    digit run, a spelled number word, a scale word or abbreviation
    (hundred, k, mil, grand), or a currency word or code."""
    low = tok.lower()
    return (
        any(c.isdigit() for c in tok)
        or low in wordlists.NUMBER_WORDS
        or low in wordlists.SCALE_WORDS
        or low in wordlists.CURRENCY_WORDS
        or tok in wordlists.CURRENCY_CODES
    )


def _isolated(toks, i):
    """A digit token is isolated only when no number-shaped token
    sits within two tokens of it ("12 fifty", "5 mil" fail)."""
    for j in (i - 2, i - 1, i + 1, i + 2):
        if 0 <= j < len(toks) and _moneyish(toks[j][2]):
            return False
    return True


def _date_parts(masked, toks, lower, years):
    """Mark every digit token that belongs to a whole-word month-name
    date: the year after a month name, the day before one ("15
    October"), the day after one ("October 3") and the day in a
    "Month D, YYYY" form. Those are the only digits allowed."""
    parts = [False] * len(toks)
    for i, (_, _, tok) in enumerate(toks):
        if not tok.isdigit():
            continue
        day = 1 <= int(tok) <= 31
        if years[i]:
            parts[i] = True
        elif day and i + 1 < len(toks) and lower[i + 1] in wordlists.MONTH_WORDS:
            parts[i] = True
        elif day and i > 0 and lower[i - 1] in wordlists.MONTH_WORDS:
            parts[i] = True
    return parts


def _whole_numbers(masked, toks, years):
    """Whole-number candidates for a numeric never-disclose item:
    every digit token, fused across gaps that hold only separators
    (",", ".", space, newline) so "1,200" and "4.2" read as the
    numbers they write. A year after a month name ends a run."""
    values = []
    i = 0
    while i < len(toks):
        if not toks[i][2].isdigit():
            i += 1
            continue
        digits = toks[i][2]
        while (
            i + 1 < len(toks)
            and toks[i + 1][2].isdigit()
            and not years[i + 1]
            and all(c in _SEP for c in masked[toks[i][1]:toks[i + 1][0]])
        ):
            i += 1
            digits += toks[i][2]
        values.append(float(digits))
        i += 1
    return values


def _numeric_item(item):
    """Coerce a never-disclose entry to a number like the money
    parser did: ``42``, ``$42``, ``1,200`` and ``42.0`` are numeric;
    anything holding letters stays a string match."""
    s = render.normalize(str(item)).strip()
    if not s or any(c.isalpha() for c in s):
        return None
    return cases.num(re.sub(r"[^0-9.\-]", "", s))


def review(find, floor, never_items):
    """Review-tier checks on the rendered message. Returns one
    plain-word reason per tripped check; reasons carry no numbers."""
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
    flags = {"mix": False, "scale": False, "currency": False,
             "commit": False, "number": False, "word": False}
    for i, (_, _, tok) in enumerate(toks):
        l = lower[i]
        flags["mix"] = (
            flags["mix"]
            or any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok)
        )
        flags["scale"] = flags["scale"] or l in wordlists.SCALE_WORDS
        flags["currency"] = (
            flags["currency"]
            or l in wordlists.CURRENCY_WORDS or tok in wordlists.CURRENCY_CODES
        )
        flags["commit"] = flags["commit"] or l in wordlists.COMMIT_WORDS
        flags["word"] = flags["word"] or l in wordlists.NUMBER_WORDS
    years = [
        toks[i][2].isdigit() and _is_year(masked, toks, i)
        for i in range(len(toks))
    ]
    dates = _date_parts(masked, toks, lower, years)
    flags["number"] = any(
        toks[i][2].isdigit()
        and not dates[i]
        and (not _small_number(toks[i][2]) or not _isolated(toks, i))
        for i in range(len(toks))
    )
    for key, msg in (
        ("mix", "a token mixing letters and digits in the message"),
        ("scale", "a scale word in the message"),
        ("currency", "a currency symbol or code in the message"),
        ("commit", "agreement or commitment wording in the message"),
        ("word", "a number word in the message"),
        ("number", "a number in the message"),
    ):
        if flags[key]:
            reasons.append(msg)
    if floor is not None and floor < 100:
        # Small integers are harmless except the one that repeats a
        # sub-100 floor's integer part, in digits or as a number word.
        fint = int(floor)
        if any(
            (
                toks[i][2].isdigit()
                and not dates[i]
                and _small_number(toks[i][2])
                and int(toks[i][2]) == fint
            )
            or wordlists.NUMBER_WORD_VALUES.get(lower[i]) == fint
            for i in range(len(toks))
        ):
            reasons.append("a number matching your limit")
    # A phrase whose first word is absent cannot match, so most
    # phrases cost one set lookup on the token set, not a scan.
    present = set(lower)
    for phrase in wordlists.COMMIT_PHRASES:
        if phrase[0] not in present:
            continue
        width = len(phrase)
        if any(
            lower[i:i + width] == list(phrase)
            for i in range(len(toks) - width + 1)
        ):
            reasons.append("agreement or commitment wording in the message")
            break
    for text, has_amount in find.fact_texts:
        if has_amount:
            continue
        words = _TOKEN.findall(text)
        if (
            any(c.isdigit() for c in text)
            or any(_moneyish(w) for w in words)
        ):
            reasons.append(
                "a fact states a number without a structured amount")
            break

    low = render.normalize(masked).lower()
    found = None
    for item in never_items:
        s = render.normalize(str(item)).strip().lower()
        if not s:
            continue
        num = _numeric_item(item)
        if num is not None:
            if found is None:
                found = _whole_numbers(masked, toks, years)
            hit = any(abs(num - v) <= FLOOR_TOL for v in found)
        else:
            hit = s in low
        if hit:
            reasons.append("a term from your never-disclose list")
            break
    return reasons
