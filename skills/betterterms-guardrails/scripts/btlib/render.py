"""Draft template rendering and the literal free-text scan.

``render(template, offer, offer_period, plan, plan_period, in_amounts)``
substitutes placeholders and returns a :class:`Find` with the rendered
message, the structured amounts it rendered, the literal segments and
any blocking errors. Placeholders are the only way money reaches a
draft:

    {offer}        draft offer, formatted with its period ("$85/month")
    {target}       plan target, with the plan period
    {option:L}     option whose label is L, with its own period
    {ladder:n}     n-th ladder entry (1-based)
    {fact:id}      plan fact text verbatim; the id joins the claims
    {quote:n}      n-th amount in the inbound ``amounts`` list

``scan_free_text`` checks a literal segment for anything money-shaped:
currency symbols or codes, currency and scale words, digit runs of 3+,
separator-joined digits, runs of number words and non-ASCII digits.
Standalone 1..99 integers pass unless they equal a floor-derived or
rendered-amount integer part. ``agreement_word`` finds phrases that
read like accepting a deal.
"""

import math
import re
import unicodedata

from . import cases, money

PERIODS = ("once", "month", "year")
_MONTHS = {"month": 1.0, "year": 12.0}
TAG = re.compile(r"\{([^{}]*)\}")

_ZW = re.compile(r"[\u200b-\u200d\ufeff\u2060]")

# Currency symbols, common letter-prefixed signs, and ISO-style codes.
_CURSYM = re.compile(r"[A-Za-z]{1,3}\$|[$€£¥₹₽฿₩₪₫₦₴₱₡]")
_CURCODE = re.compile(
    r"\b(USD|EUR|GBP|SGD|JPY|CHF|CAD|AUD|NZD|HKD|CNY|CNH|SEK|NOK|DKK|"
    r"INR|BRL|MXN|KRW|ZAR|TWD|MYR|THB|IDR|PHP|VND|AED|SAR|ILS|PLN|"
    r"CZK|HUF|TRY|RUB)\b"
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
    rf"(?:\b(?:{_NUMWORD})\b[ \t-]+){{2,}}\b(?:{_NUMWORD})\b",
    re.IGNORECASE,
)
_JOINED = re.compile(r"\d(?:[,.'` ]\d)+")
_LONG = re.compile(r"\d{3,}")
_SMALL = re.compile(r"(?<!\d)\d{1,2}(?!\d)")

_AGREEMENT = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bdeal\b",
        r"\bagreed\b",
        r"\bi\s+accept\b",
        r"\baccept\s+your\b",
        r"\bworks?\s+for\s+me\b",
        r"\bsounds\s+good[,.]?\s*let'?s\b",
        r"\bgo\s+ahead\s+and\s+charge\b",
        r"\bsign\s+me\s+up\b",
        r"\bcancel\s+my\b",
    )
]


class Value:
    """One structured amount placed by a placeholder. ``kind`` is
    ``offer``, ``target``, ``ladder``, ``option:<kind>``, ``fact`` or
    ``quote``; ``period`` is the period the value is expressed in."""

    __slots__ = ("kind", "value", "period")

    def __init__(self, kind, value, period):
        self.kind, self.value, self.period = kind, value, period


class Find:
    """The outcome of rendering a template. ``errors`` are blocking
    reasons that name the placeholder, never a number."""

    __slots__ = ("text", "values", "literal", "fact_ids", "errors")

    def __init__(self):
        self.text = None
        self.values = []
        self.literal = ""
        self.fact_ids = set()
        self.errors = []


def normalize(text):
    """NFKC plus zero-width removal: the form every check reads."""
    return _ZW.sub("", unicodedata.normalize("NFKC", text))


def convert(value, from_period, to_period):
    """Convert a value between periods for comparison. ``once`` has no
    conversion factor, so mixed once/other compares the raw value."""
    if from_period == to_period or "once" in (from_period, to_period):
        return value
    return value * _MONTHS[to_period] / _MONTHS[from_period]


def money_text(value, period=None):
    """``$1,200`` / ``$85.50`` with an optional ``/month`` or ``/year``."""
    f = float(value)
    s = f"{int(f):,}" if f.is_integer() else f"{f:,.2f}"
    if period in ("month", "year"):
        return f"${s}/{period}"
    return f"${s}"


def _parse_index(arg, what):
    if not arg.isdigit():
        return None
    n = int(arg)
    return n if n >= 1 else None


def render(template, offer, offer_period, plan, plan_period, in_amounts):
    """Render ``template``. ``in_amounts`` is the raw inbound ``amounts``
    list; entries are coerced with :func:`cases.num` at lookup time."""
    find = Find()
    out, literals = [], []
    pos = 0
    for m in TAG.finditer(template):
        literals.append(template[pos:m.start()])
        out.append(template[pos:m.start()])
        out.append(_resolve(m.group(1), find, offer, offer_period,
                            plan, plan_period, in_amounts))
        pos = m.end()
    literals.append(template[pos:])
    out.append(template[pos:])
    find.text = "".join(out)
    find.literal = "\n".join(literals)
    return find


def _resolve(tag, find, offer, offer_period, plan, plan_period, in_amounts):
    name, _, arg = tag.partition(":")
    if name == "offer" and not arg:
        if offer is None:
            find.errors.append("{offer} needs a draft offer")
            return ""
        find.values.append(Value("offer", offer, offer_period))
        return money_text(offer, offer_period)
    if name == "target" and not arg:
        v = cases.num(plan.get("target"))
        if v is None or not math.isfinite(v):
            find.errors.append("{target} has no plan value")
            return ""
        find.values.append(Value("target", v, plan_period))
        return money_text(v, plan_period)
    if name == "option" and arg:
        for item in cases.as_list(plan.get("options")):
            if isinstance(item, dict) and str(item.get("label")) == arg:
                v = cases.num(item.get("value"))
                if v is None or not math.isfinite(v):
                    find.errors.append(f"{{option:{arg}}} has no value")
                    return ""
                kind = str(item.get("kind") or "price").lower()
                period = str(item.get("period") or plan_period).lower()
                find.values.append(Value(f"option:{kind}", v, period))
                return money_text(v, period)
        find.errors.append(f"{{option:{arg}}} not in plan options")
        return ""
    if name == "ladder" and arg:
        n = _parse_index(arg, "ladder")
        items = cases.as_list(plan.get("ladder"))
        if n is None or n > len(items):
            find.errors.append(f"{{ladder:{arg}}} needs an index 1..{len(items)}")
            return ""
        item = items[n - 1]
        v = cases.num(item.get("value")) if isinstance(item, dict) else None
        if v is None or not math.isfinite(v):
            find.errors.append(f"{{ladder:{arg}}} has no value")
            return ""
        period = str(item.get("period") or plan_period).lower()
        find.values.append(Value("ladder", v, period))
        return money_text(v, period)
    if name == "fact" and arg:
        for item in cases.as_list(plan.get("facts")):
            if isinstance(item, dict) and str(item.get("id")) == arg:
                text = str(item.get("text") or "")
                find.fact_ids.add(arg)
                for v in money.amounts(text):
                    find.values.append(Value("fact", v, "once"))
                return text
        find.errors.append(f"{{fact:{arg}}} not in plan facts")
        return ""
    if name == "quote" and arg:
        n = _parse_index(arg, "quote")
        if n is None or n > len(in_amounts):
            find.errors.append(
                f"{{quote:{arg}}} needs {arg} inbound amounts"
            )
            return ""
        v = cases.num(in_amounts[n - 1])
        if v is None or not math.isfinite(v):
            find.errors.append(f"inbound amount {n} is not a number")
            return ""
        find.values.append(Value("quote", v, "once"))
        return money_text(v)
    find.errors.append(f"unknown placeholder {{{tag}}}")
    return ""


def scan_free_text(text, floor_ints, amount_ints):
    """Check a literal template segment for money-shaped content.

    ``floor_ints`` are the floor's integer part and its x12 and /12
    values; ``amount_ints`` are the integer parts of the amounts the
    placeholders rendered. Returns ``(reason, floor_related)`` or
    ``None``. The caller reports ``LIMITS`` when ``floor_related`` so the
    reason never carries a floor-derived detail."""
    s = normalize(text)
    if _CURSYM.search(s) or _CURCODE.search(s):
        return "free text contains a currency symbol or code", False
    if _CURWORD.search(s):
        return "free text contains a currency or scale word", False
    if _NUMWORD_RUN.search(s):
        return "free text contains a run of number words", False
    if any(c.isdigit() and not c.isascii() for c in s):
        return "free text contains a non-ASCII digit", False
    if _JOINED.search(s) or _LONG.search(s):
        return "free text contains a number", False
    for m in _SMALL.finditer(s):
        n = int(m.group(0))
        if n in floor_ints:
            return "limits", True
        if n in amount_ints:
            return "free text repeats a structured amount", False
    return None


def agreement_word(text):
    """The first agreement phrase in ``text``, or None."""
    for pat in _AGREEMENT:
        m = pat.search(normalize(text))
        if m:
            return m.group(0)
    return None
