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
    {quote:n}      n-th entry in the inbound ``amounts`` list: a
                   number renders as money, a string renders the
                   counterparty's words verbatim

``Find.masked`` is the rendered text with every non-fact placeholder
output replaced by a mask character; fact text stays visible because it
is user data, not a guaranteed price, and a verbatim string quote
stays visible too: inbound.yaml is written by the agent, so those
words are the agent's to vouch for and the review tier reads them
like any other free text. ``btlib.review`` scans that masked text for
the needs_approval tier.
"""

import math
import re
import unicodedata

from . import BtError, MAX_TEXT, cases

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
    the mask character; fact text stays visible inside it for the
    review tier to scan like any other free text. ``sentinel``
    marks a mask character found in the template or a fact body;
    ``oversized`` marks a render that crossed ``MAX_TEXT``: resolution
    stops, ``text`` stays None and the oversized string is never
    materialized."""

    __slots__ = ("text", "values", "masked", "fact_ids", "errors",
                 "sentinel", "oversized")

    def __init__(self):
        self.text = None
        self.values = []
        self.masked = ""
        self.fact_ids = set()
        self.errors = []
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


_SYMBOLS = {"USD": "$", "SGD": "S$", "EUR": "€", "GBP": "£"}


def money_text(value, period=None, currency="USD"):
    """``$1,200`` / ``€85.50`` / ``S$1,200`` / ``CHF 90`` with an
    optional ``/month`` or ``/year``: the declared ISO code's symbol,
    or the code itself before the number."""
    f = float(value)
    s = f"{int(f):,}" if f.is_integer() else f"{f:,.2f}"
    mark = _SYMBOLS.get(currency)
    body = f"{mark}{s}" if mark else f"{currency} {s}"
    if period in ("month", "year"):
        return f"{body}/{period}"
    return body


def _parse_index(arg):
    # str.isdigit accepts superscripts and non-ASCII digits that int()
    # either crashes on or silently misreads; indexes are ASCII only,
    # and a run longer than four digits never reaches int() at all.
    if not arg.isascii() or not arg.isdigit() or len(arg) > 4:
        return None
    return int(arg)


def _short(text):
    return text if len(text) <= 20 else text[:20] + "..."


def _enc_len(piece, find):
    """UTF-8 length of one rendered piece. A lone surrogate or any
    character UTF-8 cannot carry is a blocking error, never an
    uncaught exception: the message could never be sent verbatim.
    The replacement width only feeds the size cap."""
    try:
        return len(piece.encode("utf-8"))
    except UnicodeEncodeError:
        find.errors.append("unusual characters in the message")
        return len(piece.encode("utf-8", "replace"))


def _index(items, key):
    """First item per ``key`` value in a plan list, as a lookup dict
    built once per render so ``{option:L}`` and ``{fact:id}`` resolve
    in O(1) instead of scanning the list per placeholder."""
    index = {}
    for item in cases.as_list(items):
        if isinstance(item, dict):
            index.setdefault(str(item.get(key)), item)
    return index


def render(template, offer, offer_period, plan, plan_period,
           in_amounts, currency="USD"):
    """Render ``template``. ``in_amounts`` is the raw inbound ``amounts``
    list; entries are coerced with :func:`cases.num` at lookup time.
    The rendered byte size is summed from each piece as it resolves,
    so a fact expansion that crosses ``MAX_TEXT`` flags
    ``find.oversized``, stops resolving (a later placeholder is never
    touched) and leaves ``find.text`` unset instead of joining the
    oversized string."""
    find = Find()
    find.sentinel = _MASK in template
    options = _index(plan.get("options"), "label")
    facts = _index(plan.get("facts"), "id")
    out, masked = [], []
    size = 0
    pos = 0
    for m in TAG.finditer(template):
        literal = template[pos:m.start()]
        _bad_brace(literal, find)
        out.append(literal)
        masked.append(literal)
        size += _enc_len(literal, find)
        text, mask = _resolve(m.group(1), find, offer, offer_period,
                              plan, plan_period, in_amounts,
                              options, facts, currency)
        out.append(text)
        masked.append(mask)
        size += _enc_len(text, find)
        pos = m.end()
        if size > MAX_TEXT:
            find.oversized = True
            return find
    tail = template[pos:]
    _bad_brace(tail, find)
    out.append(tail)
    masked.append(tail)
    size += _enc_len(tail, find)
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


def _resolve(tag, find, offer, offer_period, plan, plan_period,
             in_amounts, options, facts, currency):
    """Resolve one placeholder to ``(text, masked)``: fact text passes
    through into the masked form, every other rendered value becomes
    the mask character, and an error resolves to nothing."""
    name, _, arg = tag.partition(":")
    if name == "offer" and not arg:
        if offer is None or offer <= 0:
            find.errors.append("{offer} needs a draft offer")
            return "", ""
        find.values.append(Value("offer", offer, offer_period))
        return money_text(offer, offer_period, currency), _MASK
    if name == "target" and not arg:
        v = cases.positive(plan.get("target"))
        if v is None or not math.isfinite(v):
            find.errors.append("{target} has no plan value")
            return "", ""
        find.values.append(Value("target", v, plan_period))
        return money_text(v, plan_period, currency), _MASK
    if name == "option" and arg:
        item = options.get(arg)
        if item is None:
            find.errors.append(f"{{option:{arg}}} not in plan options")
            return "", ""
        v = cases.positive(item.get("value"))
        if v is None or not math.isfinite(v):
            find.errors.append(f"{{option:{arg}}} has no value")
            return "", ""
        kind = str(item.get("kind") or "price").lower()
        period = str(item.get("period") or plan_period).lower()
        find.values.append(Value(f"option:{kind}", v, period))
        return money_text(v, period, currency), _MASK
    if name == "ladder" and arg:
        n = _parse_index(arg)
        items = cases.as_list(plan.get("ladder"))
        if n is None:
            find.errors.append(
                f"malformed placeholder {{ladder:{_short(arg)}}}")
            return "", ""
        if not 1 <= n <= len(items):
            find.errors.append(f"{{ladder:{arg}}} needs an index 1..{len(items)}")
            return "", ""
        item = items[n - 1]
        v = cases.positive(item.get("value")) if isinstance(item, dict) else None
        if v is None or not math.isfinite(v):
            find.errors.append(f"{{ladder:{arg}}} has no value")
            return "", ""
        period = str(item.get("period") or plan_period).lower()
        find.values.append(Value("ladder", v, period))
        return money_text(v, period, currency), _MASK
    if name == "fact" and arg:
        item = facts.get(arg)
        if item is None:
            find.errors.append(f"{{fact:{arg}}} not in plan facts")
            return "", ""
        text = str(item.get("text") or "")
        if _MASK in text:
            find.sentinel = True
        find.fact_ids.add(arg)
        # Hard blocks read the structured amount only; the
        # fact text renders verbatim for the user and the
        # review tier, never for a money parse. An amount that
        # is set but not a usable number is a blocking error,
        # never a null: check_plan_limits exits 2 first, and a
        # direct render must not treat it as absent either.
        v = cases.positive(item.get("amount"))
        if item.get("amount") is not None and v is None:
            find.errors.append(
                f"{{fact:{arg}}} amount is not a number")
            return "", ""
        if v is not None and math.isfinite(v):
            period = str(item.get("period") or "once").lower()
            find.values.append(Value("fact", v, period))
        return text, text
    if name == "quote" and arg:
        n = _parse_index(arg)
        if n is None:
            find.errors.append(
                f"malformed placeholder {{quote:{_short(arg)}}}")
            return "", ""
        if not 1 <= n <= len(in_amounts):
            find.errors.append(
                f"{{quote:{arg}}} needs {arg} inbound amounts"
            )
            return "", ""
        entry = in_amounts[n - 1]
        if isinstance(entry, str):
            # A string entry is the counterparty's words as the agent
            # recorded them: it renders verbatim and stays visible in
            # the masked text like a fact body, because inbound.yaml
            # is agent-written and the review tier must read those
            # words like the agent's own. It carries no amount, so
            # the floor rules never read it as an offer (spec 4.4).
            if _MASK in entry:
                find.sentinel = True
            return entry, entry
        v = cases.positive(entry)
        if v is None or not math.isfinite(v):
            find.errors.append(f"inbound amount {n} is not a number")
            return "", ""
        find.values.append(Value("quote", v, "once"))
        return money_text(v, None, currency), _MASK
    find.errors.append(f"unknown placeholder {{{tag}}}")
    return "", ""
