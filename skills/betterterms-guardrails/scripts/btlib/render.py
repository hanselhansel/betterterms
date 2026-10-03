"""Draft template rendering.

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
is user data, not a guaranteed price. ``btlib.review`` scans that
masked text for the needs_approval tier.
"""

import math
import re
import unicodedata

from . import BtError, MAX_TEXT, cases, money

_MONTHS = {"month": 1.0, "year": 12.0}
TAG = re.compile(r"\{([^{}]*)\}")

# One private-use character stands in for each non-fact placeholder
# output. It sits outside the user's allowed set, so a sentinel the
# template or a fact itself carries is flagged instead of passing for
# rendered money.
_MASK = "\ue000"


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
    fact id so a repeated {fact:id} costs once. ``sentinel`` marks a
    mask character found in the template or a fact body; ``oversized``
    marks a render that crossed ``MAX_TEXT``, in which case ``text``
    stays None: the size is summed from piece lengths, so the
    oversized string is never materialized."""

    __slots__ = ("text", "values", "masked", "fact_ids", "errors",
                 "fact_amounts", "sentinel", "oversized")

    def __init__(self):
        self.text = None
        self.values = []
        self.masked = ""
        self.fact_ids = set()
        self.errors = []
        self.fact_amounts = {}
        self.sentinel = False
        self.oversized = False


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
    list; entries are coerced with :func:`cases.num` at lookup time.
    The rendered byte size is summed from each piece as it resolves,
    so a fact expansion that crosses ``MAX_TEXT`` flags
    ``find.oversized`` and leaves ``find.text`` unset instead of
    joining the oversized string."""
    find = Find()
    find.sentinel = _MASK in template
    out, masked = [], []
    size = 0
    pos = 0
    for m in TAG.finditer(template):
        literal = template[pos:m.start()]
        _bad_brace(literal, find)
        out.append(literal)
        masked.append(literal)
        size += len(literal.encode("utf-8"))
        text, mask = _resolve(m.group(1), find, offer, offer_period,
                              plan, plan_period, in_amounts)
        out.append(text)
        masked.append(mask)
        size += len(text.encode("utf-8"))
        pos = m.end()
    tail = template[pos:]
    _bad_brace(tail, find)
    out.append(tail)
    masked.append(tail)
    size += len(tail.encode("utf-8"))
    if size > MAX_TEXT:
        find.oversized = True
    else:
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
                if _MASK in text:
                    find.sentinel = True
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
