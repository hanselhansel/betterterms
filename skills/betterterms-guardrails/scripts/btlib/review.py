"""The review-tier text scan: an allowlist, not a blacklist.

``review(find, never_items)`` reads ``find.masked`` (each non-fact
placeholder output replaced by :data:`render._MASK`, fact text and
verbatim string quotes visible: inbound.yaml is agent-written, so a
quoted string is the agent's to vouch for) and ``find.values``, and
returns one plain-word reason per
tripped check; reasons carry no numbers. The 0010 amendment keeps
the tier simple and strict: any ASCII digit in the free text or in a
rendered fact's text, any number word or scale word stem inside a
lowercased letter run (outside the listed common-English
exceptions), any scale word, currency word or code, any commitment
word or phrase, characters off the allowed set, glue on a rendered
amount and every ``never_disclose`` term all route to the user. A numeric
``never_disclose`` item also compares against the rendered
placeholder values, so the term still matches behind the mask. There
is no digit parsing in this tier: a digit run of any length is a
match, never a number to read, so nothing here can crash on
``int()`` or stall on a huge token.
"""

import bisect
import re

from . import FLOOR_TOL, cases, quotes, render, wordlists

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
# backtracking. Interior apostrophes stay inside the token so "i'll
# take" matches the commitment phrase and "won't" is not "won".
_TOKEN = re.compile(r"[0-9A-Za-z]+(?:'[0-9A-Za-z]+)*")
# Lowercase letter runs for the number-word and scale-stem
# substring checks.
_LETTERS = re.compile(r"[a-z]+")
# The digit rule: one ASCII digit anywhere is a match.
_DIGIT = re.compile(r"[0-9]")
_SEP = ",. \n"


def _touching(text):
    """Glue that could extend a rendered amount sits right against a
    mask sentinel: a letter ("$1,100k" reads as 1,100,000) or a
    ``.``/``,`` separator with a digit on its far side
    ("$1,100.99"). A bare digit on the sentinel is already caught by
    the digit scan, so it is not repeated here."""
    for i, c in enumerate(text):
        if c != render._MASK:
            continue
        for j in (i - 1, i + 1):
            if not 0 <= j < len(text):
                continue
            d = text[j]
            if d.isascii() and d.isalpha():
                return True
            if d in ".,":
                k = j + (j - i)  # the character past the separator
                if (0 <= k < len(text) and text[k].isascii()
                        and text[k].isdigit()):
                    return True
    return False


def _tokens(text):
    """All alphanumeric tokens of ``text`` as ``(start, end, token)``
    in order: one linear pass, no backtracking."""
    return [(m.start(), m.end(), m.group(0)) for m in _TOKEN.finditer(text)]


# A possessive or contraction suffix hides the list word behind it:
# "deal's", "dollar's", "USD's", "k's". Each strips once per pass so
# stacked forms still reach the word; "'t" alone never strips, so
# "won't" reads as "wo", never the currency "won".
_SUFFIXES = ("'s", "'ll", "'re", "'ve", "'d", "'m", "n't")


def _word_forms(tok):
    """The token plus each form an apostrophe suffix uncovers, raw
    case kept so the currency codes still match case-sensitively."""
    forms = [tok]
    t = tok
    while True:
        for suf in _SUFFIXES:
            low = t.lower()
            if low.endswith(suf) and len(low) > len(suf):
                t = t[: -len(suf)]
                forms.append(t)
                break
        else:
            return forms


def _number_word_hit(run):
    """A lowercased letter run is number-shaped when it contains a
    number word as a substring ("twelvehundred", "fiftyish",
    "twentyone") and is not a listed common English word ("often",
    "money"). The exception is whole-run only, so "oftener" still
    flags."""
    if run in wordlists.NUMBER_WORD_EXCEPTIONS:
        return False
    return any(w in run for w in wordlists.NUMBER_WORDS)


def _scale_word_hit(run):
    """A lowercased letter run is scale-shaped when it contains a
    scale word stem ("halfmillion", "thousandfold", "hundredish",
    "grandtotal") and is not a listed common English word. The one-
    and two-letter abbreviations stay whole-token: inside a run they
    are ordinary letters ("milk", "family")."""
    if run in wordlists.NUMBER_WORD_EXCEPTIONS:
        return False
    return any(w in run for w in wordlists.SCALE_WORD_STEMS)


def _digit_groups(masked, toks):
    """Digit runs for a numeric never-disclose item: consecutive
    digit tokens joined over gaps that hold only separators (",",
    ".", space, newline) fuse into one digit string, so "1,200" and
    "12 00" read as "1200". Nothing is parsed: groups stay strings
    and compare as strings."""
    groups = []
    i = 0
    while i < len(toks):
        if toks[i][2].isdigit():
            start = i
            while (
                i + 1 < len(toks)
                and toks[i + 1][2].isdigit()
                and all(c in _SEP
                        for c in masked[toks[i][1]:toks[i + 1][0]])
            ):
                i += 1
            groups.append("".join(t[2] for t in toks[start:i + 1]))
        i += 1
    return groups


def _numeric_item(item):
    """Coerce a never-disclose entry to a number like the money
    parser did: ``42``, ``$42``, ``1,200`` and ``42.0`` are numeric;
    anything holding letters stays a string match."""
    s = render.normalize(str(item)).strip()
    if not s or any(c.isalpha() for c in s):
        return None
    return cases.num(re.sub(r"[^0-9.\-]", "", s))


def disclosed(rendered, never_items):
    """True when a ``never_disclose`` item with letters appears in the
    rendered text, verbatim quote text included: a listed term like
    "CHF 90" or "$85/month" is never a coincidence, so the gate
    treats the hit as a hard block, not a review item. Numeric items
    stay in the review tier: they compare against digit runs and
    rendered values in ``review``."""
    if not rendered:
        return False
    low = render.normalize(rendered).lower()
    for item in never_items:
        s = render.normalize(str(item)).strip().lower()
        if s and any(c.isalpha() for c in s) and s in low:
            return True
    return False


# Words that turn a commitment phrase into a decline when they sit
# within the two tokens before it: "no longer works for me",
# "won't take it". Contraction forms are covered by the n't suffix.
_NEGATORS = frozenset(
    "no not never without cannot".split()
)


def _negated(lower, i):
    """True when a negator sits within the two tokens before ``i``."""
    return any(
        t in _NEGATORS or t.endswith("n't")
        for t in lower[max(0, i - 2):i]
    )


def review(find, never_items):
    """Review-tier checks on the rendered message. Returns one
    plain-word reason per tripped check; reasons carry no numbers."""
    reasons = []
    masked = find.masked
    if find.sentinel or any(c not in _ALLOWED for c in masked):
        reasons.append("unusual characters in the message")
    if _DIGIT.search(masked):
        reasons.append("numbers in the message")
    if _touching(masked):
        reasons.append("text touches a rendered amount")
    toks = _tokens(masked)
    lower = [t.lower() for _, _, t in toks]
    flags = {"scale": False, "currency": False, "commit": False}
    for i, (_, _, tok) in enumerate(toks):
        forms = _word_forms(tok)
        lows = [f.lower() for f in forms]
        flags["scale"] = flags["scale"] or any(
            f in wordlists.SCALE_WORDS for f in lows
        )
        flags["currency"] = (
            flags["currency"]
            or any(f in wordlists.CURRENCY_WORDS for f in lows)
            or any(f in wordlists.CURRENCY_CODES for f in forms)
        )
        flags["commit"] = flags["commit"] or any(
            f in wordlists.COMMIT_WORDS for f in lows
        )
    runs = _LETTERS.findall(masked.lower())
    flags["scale"] = flags["scale"] or any(
        _scale_word_hit(run) for run in runs
    )
    for key, msg in (
        ("scale", "a scale word in the message"),
        ("currency", "a currency symbol or code in the message"),
        ("commit", "agreement or commitment wording in the message"),
    ):
        if flags[key]:
            reasons.append(msg)
    if any(_number_word_hit(run) for run in runs):
        reasons.append("a number word in the message")
    # A phrase whose first word is absent cannot match, so most
    # phrases cost one set lookup on the token set, not a scan. A
    # match directly negated within the two tokens before it is a
    # decline, not a commitment: "no longer works for me" does not
    # promise anything (spec 4.3's template self-check relies on
    # this).
    present = set(lower)
    for phrase in wordlists.COMMIT_PHRASES:
        if phrase[0] not in present:
            continue
        width = len(phrase)
        if any(
            lower[i:i + width] == list(phrase)
            and not _negated(lower, i)
            for i in range(len(toks) - width + 1)
        ):
            reasons.append("agreement or commitment wording in the message")
            break

    low = render.normalize(masked).lower()
    groups = None
    values = None
    for item in never_items:
        s = render.normalize(str(item)).strip().lower()
        if not s:
            continue
        num = _numeric_item(item)
        if num is not None:
            if groups is None:
                groups = frozenset(_digit_groups(masked, toks))
                values = sorted(v.value for v in find.values)
            # The item's digits match a fused text run as a whole
            # string ("42" hits "42" and "4.2", not "420"), and its
            # value matches a rendered placeholder amount behind the
            # mask. A set lookup and a bisect keep thousands of items
            # linear on a 64 KB input; the value within tolerance is
            # always the left or right bisection neighbour.
            i = bisect.bisect_left(values, num)
            hit = re.sub(r"[^0-9]", "", s) in groups or (
                i < len(values) and values[i] - num <= FLOOR_TOL
            ) or (i > 0 and num - values[i - 1] <= FLOOR_TOL)
        else:
            # A lettered item is a hard-block check (``disclosed``);
            # the review-tier hit stays as defence in depth: the
            # reason reports once either way.
            hit = s in low
        if hit:
            reasons.append("a term from your never-disclose list")
            break
    return reasons
