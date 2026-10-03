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
needs_approval tier: anything money-shaped, numeric, committal or
invisible that is not a rendered placeholder goes to the user.
"""

import math
import re
import unicodedata

from . import BtError, cases, money

PERIODS = ("once", "month", "year")
_MONTHS = {"month": 1.0, "year": 12.0}
TAG = re.compile(r"\{([^{}]*)\}")

_MASK = "\x00"  # stands in for one non-fact placeholder output

# Currency symbols, common letter-prefixed signs, and ISO-style codes.
_CURSYM = re.compile(r"[A-Za-z]{1,3}\$|[$€£¥₹₽฿₩₪₫₦₴₱₡]")
_CODES = (
    "USD|EUR|GBP|SGD|JPY|CHF|CAD|AUD|NZD|HKD|CNY|CNH|SEK|NOK|DKK|"
    "INR|BRL|MXN|KRW|ZAR|TWD|MYR|THB|IDR|PHP|VND|AED|SAR|ILS|PLN|"
    "CZK|HUF|TRY|RUB"
)
_CURCODE = re.compile(rf"\b(?:{_CODES})\b")
# Lowercase codes flag too, except the ones that are also common words
# ("try", "rub", "cad"): they stay uppercase-only.
_CURCODE_CI = re.compile(
    r"\b(?:usd|eur|gbp|sgd|jpy|chf|aud|nzd|hkd|cny|cnh|sek|nok|dkk|"
    r"inr|brl|mxn|krw|zar|twd|myr|thb|idr|php|vnd|aed|sar|ils|pln|"
    r"czk|huf)\b",
    re.IGNORECASE,
)
_CURWORD = re.compile(
    r"\b(dollars?|bucks?|euros?|pounds?|yen|yuan|renminbi|grand|quid|"
    r"hundred|thousand|millions?|billions?|trillions?|bn|mm)\b|"
    r"\d\s*k\b",
    re.IGNORECASE,
)
_NUMWORD = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"oh|ought|nil"
)
_NUMWORD_RUN = re.compile(
    rf"(?:\b(?:{_NUMWORD})\b[ \t-]+)+\b(?:{_NUMWORD})\b",
    re.IGNORECASE,
)
# Three or more digits, separators allowed between any of them.
_NUM3 = re.compile(r"\d(?:[,.'` ]*\d){2,}")
_SMALL = re.compile(r"(?<!\d)\d{1,2}(?!\d)")
_ADJACENT = re.compile(r"\d\x00|\x00\d")

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
# A 4-digit year next to a month name is a date, not an amount.
_DATE = re.compile(
    rf"\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s*(?:19|20)\d\d\b|"
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\s*,?\s*(?:19|20)\d\d\b|"
    rf"\b{_MONTH}\s+(?:19|20)\d\d\b",
    re.IGNORECASE,
)

_COMMIT = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bdeal\b",
        r"\bagree\w*\b",
        r"\baccept\w*\b",
        r"\bworks?\s+for\s+(me|us)\b",
        r"\b(?:happy|glad|willing|ready)\s+to\s+pay\b",
        r"\bpay\b",
        r"\bgo\s+ahead\b",
        r"\bcharge\b",
        r"\bprocess\s+it\b",
        r"\bsign\s+me\s+up\b",
        r"\bcancel\s+my\b",
        r"\bconfirm\w*\b",
        r"\bsounds\s+good\b",
    )
]

# Invisible joiners outside category Cf: the combining grapheme joiner,
# Mongolian free variation selectors and variation selectors.
_MN_JOINERS = frozenset(
    "\u034f\u180b\u180c\u180d\u180e\u180f"
    "\ufe00\ufe01\ufe02\ufe03\ufe04\ufe05\ufe06\ufe07"
    "\ufe08\ufe09\ufe0a\ufe0b\ufe0c\ufe0d\ufe0e\ufe0f"
)


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
    the mask character."""

    __slots__ = ("text", "values", "masked", "fact_ids", "errors")

    def __init__(self):
        self.text = None
        self.values = []
        self.masked = ""
        self.fact_ids = set()
        self.errors = []


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


def _parse_index(arg, what):
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
        n = _parse_index(arg, "ladder")
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
                for v in money.amounts(text):
                    find.values.append(Value("fact", v, "once"))
                return text, text
        find.errors.append(f"{{fact:{arg}}} not in plan facts")
        return "", ""
    if name == "quote" and arg:
        n = _parse_index(arg, "quote")
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


def _invisible(ch):
    """Format (Cf) characters, Mn joiners and variation selectors."""
    return unicodedata.category(ch) == "Cf" or ch in _MN_JOINERS


def _touching(text):
    """A character that could extend a rendered amount sits right
    against a mask sentinel: a letter or digit ("$1,100k" reads as
    1,100,000), or a ``.``/``,`` separator with a digit on its far
    side ("$1,100.99" restates the price). A separator followed by a
    space or a word is ordinary sentence punctuation, not glue."""
    for i, c in enumerate(text):
        if c != _MASK:
            continue
        for j in (i - 1, i + 1):
            if not 0 <= j < len(text):
                continue
            d = text[j]
            if d.isalnum():
                return True
            if d in ".,":
                k = j + (j - i)  # the character past the separator
                if 0 <= k < len(text) and text[k].isdigit():
                    return True
    return False


def review(find, floor, never_items):
    """Review-tier checks on the rendered message. Reads ``find.masked``
    (placeholder outputs masked, fact text visible) and returns one
    plain-word reason per tripped check; reasons carry no numbers."""
    reasons = []
    masked = find.masked
    if any(_invisible(c) for c in masked):
        reasons.append("invisible or format characters in the message")
    if any(c.isdigit() and not c.isascii() for c in masked):
        reasons.append("non-ASCII digits in the message")
    norm = normalize(masked)
    if _ADJACENT.search(norm):
        reasons.append("a digit next to a rendered amount")
    if _touching(norm):
        reasons.append("text touches a rendered amount")
    if (
        _CURSYM.search(norm)
        or _CURCODE.search(norm)
        or _CURCODE_CI.search(norm)
    ):
        reasons.append("a currency symbol or code in the message")
    if _CURWORD.search(norm):
        reasons.append("a money or scale word in the message")
    if _NUMWORD_RUN.search(norm):
        reasons.append("a run of number words in the message")
    work = _DATE.sub(" ", norm)
    if _NUM3.search(work):
        reasons.append("a number in the message")
    elif floor is not None and floor < 100:
        # Small integers are harmless except the one that repeats a
        # sub-100 floor's integer part.
        fint = int(floor)
        if any(int(m.group(0)) == fint for m in _SMALL.finditer(work)):
            reasons.append("a number matching your limit")
    if any(p.search(norm) for p in _COMMIT):
        reasons.append("agreement or commitment wording in the message")

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
