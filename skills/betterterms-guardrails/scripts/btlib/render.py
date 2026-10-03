"""Draft template rendering and the review-tier text scan.

``render(template, offer, offer_period, plan, plan_period, in_amounts)``
substitutes placeholders and returns a :class:`Find` with the rendered
message, the structured amounts it rendered, a masked form of the
message and any blocking errors. Placeholders are the only way money
reaches a draft:

    {offer}        draft offer, formatted with its period ("$85/month")
    {target}       plan target, with the plan period
    {option:L}     option whose label is L, with its own period
    {ladder:n}     n-th ladder entry (1-based)
    {fact:id}      plan fact text verbatim; the id joins the claims
    {quote:n}      n-th amount in the inbound ``amounts`` list

``Find.masked`` is the rendered text with every non-fact placeholder
output replaced by a mask character; fact text stays visible because it
is user data, not a guaranteed price. ``review`` scans that masked
text and returns plain-word reasons (never a number) for the
needs_approval tier. The scan is an allowlist, not a blacklist:
every character must be on the allowed set and every alphanumeric
token must be clean (decision 0009 amendment).
"""

import math
import re
import unicodedata

from . import BtError, cases, money, wordlists

PERIODS = ("once", "month", "year")
_MONTHS = {"month": 1.0, "year": 12.0}
TAG = re.compile(r"\{([^{}]*)\}")

_MASK = "\x00"  # stands in for one non-fact placeholder output

# The review-tier allowlist: ASCII letters and digits, space and
# newline, this punctuation set and the sentinel. Any other character
# (non-ASCII letters, homoglyphs, controls, format, combining and
# private-use characters, currency signs, symbols) routes to the user,
# which is why non-English text always needs approval.
_ALLOWED = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    " \n.,;:!?'\"()-/&" + _MASK
)
# Free text splits into alphanumeric runs: one linear pass, no
# backtracking.
_TOKEN = re.compile(r"[0-9A-Za-z]+")


class Value:
    """One structured amount placed by a placeholder. ``kind`` is
    ``offer``, ``target``, ``ladder``, ``option:<kind>``, ``fact`` or
    ``quote``; ``period`` is the period the value is expressed in."""

    __slots__ = ("kind", "value", "period")

    def __init__(self, kind, value, period):
        self.kind, self.value, self.period = kind, value, period


class Find:
    """The outcome of rendering a template. ``errors`` are blocking
    reasons that name the placeholder, never a number. ``masked`` is
    the rendered text with non-fact placeholder outputs replaced by
    the mask character. ``fact_amounts`` caches one money scan per
    fact id so a repeated {fact:id} costs once."""

    __slots__ = ("text", "values", "masked", "fact_ids", "errors",
                 "fact_amounts")

    def __init__(self):
        self.text = None
        self.values = []
        self.masked = ""
        self.fact_ids = set()
        self.errors = []
        self.fact_amounts = {}


def normalize(text):
    """NFKC plus removal of format (Cf) characters: the form every
    word-level check reads."""
    return "".join(
        c
        for c in unicodedata.normalize("NFKC", text)
        if unicodedata.category(c) != "Cf"
    )


def convert(value, from_period, to_period):
    """Convert a value between periods for comparison. ``once`` has no
    conversion factor, so mixed once/other compares the raw value."""
    if from_period == to_period or "once" in (from_period, to_period):
        return value
    if from_period not in _MONTHS or to_period not in _MONTHS:
        raise BtError("invalid option period")
    return value * _MONTHS[to_period] / _MONTHS[from_period]


def money_text(value, period=None):
    """``$1,200`` / ``$85.50`` with an optional ``/month`` or ``/year``."""
    f = float(value)
    s = f"{int(f):,}" if f.is_integer() else f"{f:,.2f}"
    if period in ("month", "year"):
        return f"${s}/{period}"
    return f"${s}"


def _parse_index(arg):
    # str.isdigit accepts superscripts and non-ASCII digits that int()
    # either crashes on or silently misreads; indexes are ASCII only.
    if not arg.isascii() or not arg.isdigit():
        return None
    n = int(arg)
    return n if n >= 1 else None


def render(template, offer, offer_period, plan, plan_period, in_amounts):
    """Render ``template``. ``in_amounts`` is the raw inbound ``amounts``
    list; entries are coerced with :func:`cases.num` at lookup time."""
    find = Find()
    out, masked = [], []
    pos = 0
    for m in TAG.finditer(template):
        literal = template[pos:m.start()]
        _bad_brace(literal, find)
        out.append(literal)
        masked.append(literal)
        text, mask = _resolve(m.group(1), find, offer, offer_period,
                              plan, plan_period, in_amounts)
        out.append(text)
        masked.append(mask)
        pos = m.end()
    tail = template[pos:]
    _bad_brace(tail, find)
    out.append(tail)
    masked.append(tail)
    find.text = "".join(out)
    find.masked = "".join(masked)
    return find


def _bad_brace(seg, find):
    """Literal template text may not contain a brace: an unmatched or
    nested ``{``/``}`` is a malformed placeholder, never sendable."""
    i = min((seg.find(c) for c in "{}" if c in seg), default=-1)
    if i < 0:
        return
    frag = seg[i:i + 40] if seg[i] == "{" else seg[max(0, i - 39):i + 1]
    find.errors.append(f"malformed placeholder {frag.strip()}")


def _resolve(tag, find, offer, offer_period, plan, plan_period, in_amounts):
    """Resolve one placeholder to ``(text, masked)``: fact text passes
    through into the masked form, every other rendered value becomes
    the mask character, and an error resolves to nothing."""
    name, _, arg = tag.partition(":")
    if name == "offer" and not arg:
        if offer is None:
            find.errors.append("{offer} needs a draft offer")
            return "", ""
        find.values.append(Value("offer", offer, offer_period))
        return money_text(offer, offer_period), _MASK
    if name == "target" and not arg:
        v = cases.num(plan.get("target"))
        if v is None or not math.isfinite(v):
            find.errors.append("{target} has no plan value")
            return "", ""
        find.values.append(Value("target", v, plan_period))
        return money_text(v, plan_period), _MASK
    if name == "option" and arg:
        for item in cases.as_list(plan.get("options")):
            if isinstance(item, dict) and str(item.get("label")) == arg:
                v = cases.num(item.get("value"))
                if v is None or not math.isfinite(v):
                    find.errors.append(f"{{option:{arg}}} has no value")
                    return "", ""
                kind = str(item.get("kind") or "price").lower()
                period = str(item.get("period") or plan_period).lower()
                find.values.append(Value(f"option:{kind}", v, period))
                return money_text(v, period), _MASK
        find.errors.append(f"{{option:{arg}}} not in plan options")
        return "", ""
    if name == "ladder" and arg:
        n = _parse_index(arg)
        items = cases.as_list(plan.get("ladder"))
        if n is None or n > len(items):
            find.errors.append(f"{{ladder:{arg}}} needs an index 1..{len(items)}")
            return "", ""
        item = items[n - 1]
        v = cases.num(item.get("value")) if isinstance(item, dict) else None
        if v is None or not math.isfinite(v):
            find.errors.append(f"{{ladder:{arg}}} has no value")
            return "", ""
        period = str(item.get("period") or plan_period).lower()
        find.values.append(Value("ladder", v, period))
        return money_text(v, period), _MASK
    if name == "fact" and arg:
        for item in cases.as_list(plan.get("facts")):
            if isinstance(item, dict) and str(item.get("id")) == arg:
                text = str(item.get("text") or "")
                find.fact_ids.add(arg)
                if arg not in find.fact_amounts:
                    find.fact_amounts[arg] = money.amounts(text)
                for v in find.fact_amounts[arg]:
                    find.values.append(Value("fact", v, "once"))
                return text, text
        find.errors.append(f"{{fact:{arg}}} not in plan facts")
        return "", ""
    if name == "quote" and arg:
        n = _parse_index(arg)
        if n is None or n > len(in_amounts):
            find.errors.append(
                f"{{quote:{arg}}} needs {arg} inbound amounts"
            )
            return "", ""
        v = cases.num(in_amounts[n - 1])
        if v is None or not math.isfinite(v):
            find.errors.append(f"inbound amount {n} is not a number")
            return "", ""
        find.values.append(Value("quote", v, "once"))
        return money_text(v), _MASK
    find.errors.append(f"unknown placeholder {{{tag}}}")
    return "", ""


def _touching(text):
    """Characters that could extend a rendered amount sit right
    against a mask sentinel. Returns the kinds found: ``digit`` for a
    digit directly on the sentinel ("$1,100" plus "0" restates the
    price), ``letter`` for a letter ("$1,100k" reads as 1,100,000) and
    ``decimal`` for a ``.``/``,`` separator with a digit on its far
    side ("$1,100.99"). An empty set means the sentinel is clean."""
    found = set()
    for i, c in enumerate(text):
        if c != _MASK:
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


def review(find, floor, never_items):
    """Review-tier checks on the rendered message. Reads ``find.masked``
    (placeholder outputs masked, fact text visible) and returns one
    plain-word reason per tripped check; reasons carry no numbers.
    The scan is an allowlist: characters off the permitted set, tokens
    that mix letters and digits, disallowed numbers, listed money and
    commitment words and sentinel glue all go to the user."""
    reasons = []
    masked = find.masked
    if any(c not in _ALLOWED for c in masked):
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
        elif tok.isdigit() and not (
            (len(tok) <= 4 and 1 <= int(tok) <= 99)
            or _is_year(masked, toks, i)
        ):
            reasons.append("a number in the message")
        l = lower[i]
        if l in wordlists.SCALE_WORDS:
            reasons.append("a scale word in the message")
        if l in wordlists.CURRENCY_WORDS or tok in wordlists.CURRENCY_CODES:
            reasons.append("a currency symbol or code in the message")
        if l in wordlists.COMMIT_WORDS:
            reasons.append("agreement or commitment wording in the message")
        if l == "k" and i > 0 and toks[i - 1][2].isdigit():
            reasons.append("a scale word in the message")
    for i in range(len(toks) - 1):
        if (
            lower[i] in wordlists.NUMBER_WORDS
            and lower[i + 1] in wordlists.NUMBER_WORDS
            and all(c in " \t-" for c in masked[toks[i][1]:toks[i + 1][0]])
        ):
            reasons.append("a run of number words in the message")
            break
    if floor is not None and floor < 100:
        # Small integers are harmless except the one that repeats a
        # sub-100 floor's integer part.
        fint = int(floor)
        if any(
            t.isdigit() and len(t) <= 4 and int(t) == fint
            for _, _, t in toks
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

    norm = normalize(masked)
    low = norm.lower()
    found_amounts = None
    for item in never_items:
        s = normalize(str(item)).strip().lower()
        if not s:
            continue
        vals = [] if any(c.isalpha() for c in s) else money.amounts(s)
        if vals:
            # Numeric items match as whole numbers only.
            if found_amounts is None:
                found_amounts = money.amounts(norm)
            hit = any(abs(v - a) <= 0.005 for v in vals for a in found_amounts)
        else:
            hit = s in low
        if hit:
            reasons.append("a term from your never-disclose list")
            break
    return reasons
