"""The quote-amount rule and the rendered-value floor checks
(decision 0016, spec 4.4).

A ``{quote:n}`` placeholder restates something the counterparty
wrote: a numeric entry in the inbound ``amounts`` list renders as
money like any structured value; a string entry renders the words
verbatim and joins ``find.quote_spans``. Either way a quote is never
the agent's own offer, so the worse-than-floor and
unconvertible-period checks never reach it on any action. Equality
with the floor still blocks: a rendered value equal to the walk-away
number leaks it regardless of who wrote it. The rendered text is
still scanned, so a ``never_disclose`` term inside a verbatim quote
blocks like anywhere else.

The floor rules on rendered placeholder values live here too:
``check_values`` applies them to the values ``render.render``
placed, ``converted_match`` and ``floor_digits`` back the review
tier's converted-limit and same-digits reasons.
"""

import re
from decimal import Decimal

from . import FLOOR_TOL, LIMITS, minor, render

# Placeholder value kinds whose amount is the agent's own price:
# target, ladder and price options always; fact amounts on an
# agreeing action (on ``send`` a fact restates what was already on
# the table). Quotes are absent by design (spec 4.4).
PRICE_KINDS = ("target", "ladder", "option:price", "fact")

_DIGIT_RUN = re.compile(r"[0-9]+")
_SEP = ",. \n"


def worse(value, floor, direction):
    return (
        value < floor - FLOOR_TOL
        if direction == "receive"
        else value > floor + FLOOR_TOL
    )


def same(a, values):
    return any(abs(a - v) <= FLOOR_TOL for v in values)


def in_floor_period(value, from_period, plan_period):
    """``value`` as it renders (minor unit), converted and rounded
    again: comparisons always read rendered amounts."""
    return minor(render.convert(minor(value), from_period, plan_period))


def check_values(find, action, floor, direction, plan_period, findings):
    """Floor rules on the amounts the placeholders placed: every value
    except the offer itself must not equal the floor (in its own or
    the floor's period), and a price value (target, ladder, price
    option, or fact amount off ``send``) must not be worse than the
    floor. Fact amounts come from the structured ``amount`` field
    only, never parsed text (decision 0010). Equality with only a
    period conversion is a review hit, not a block; it is checked in
    ``converted_match`` under the review tier. Bonus and fee options
    are not offers, so only the equality rule reaches them. A price
    value whose period cannot convert to the floor's (``once`` on
    either side) fails closed like an unconvertible offer. A quote
    is exempt from both price checks on every action (spec 4.4)."""
    for v in find.values:
        quoted = v.kind == "fact" and action == "send"
        priced = v.kind in PRICE_KINDS and not quoted
        if priced and v.period != plan_period and "once" in (
            v.period, plan_period
        ):
            findings.append(("block", "period differs from your limit"))
            continue
        nv = in_floor_period(v.value, v.period, plan_period)
        if v.kind != "offer" and (
            same(nv, (floor,)) or same(minor(v.value), (floor,))
        ):
            findings.append(("block", LIMITS))
        elif priced and worse(nv, floor, direction):
            findings.append(("block", LIMITS))


def converted_match(find, floor, plan_period):
    """True when a rendered non-offer value equals the floor's x12 or
    /12 conversion in its own or the floor's period, without equalling
    the floor itself: "5/year" against a 60/month floor is a numeric
    coincidence the user must see, not proof of a leak."""
    for v in find.values:
        if v.kind == "offer":
            continue
        nv = in_floor_period(v.value, v.period, plan_period)
        for val in (nv, minor(v.value)):
            if same(val, (floor * 12, floor / 12)) and not same(
                val, (floor,)
            ):
                return True
    return False


def floor_digits(find, floor, plan_period, action):
    """True when the rendered offer repeats the floor's digits in a
    period that is not the floor's: "$1,200/year" next to a
    1,200/month floor is a coincidence the user must judge, not a
    clean pass. A match in the floor's own period already routes as
    "offer is at your limit" and a non-offer value equal to the floor
    blocks outright, so only the offer needs this check. ``accept``,
    ``sign`` and ``pay`` are exempt: they may restate a price the
    counterparty already named."""
    if action in OFFERED:
        return False
    for v in find.values:
        if v.kind != "offer":
            continue
        nv = in_floor_period(v.value, v.period, plan_period)
        if same(minor(v.value), (floor,)) and not same(nv, (floor,)):
            return True
    return False


OFFERED = {"accept", "pay", "sign"}


def quote_amounts(rendered_spans):
    """The amounts inside rendered quote spans, as Decimals: each
    maximal run of digit tokens fused over ``,`` ``.`` and whitespace
    separators becomes one amount ("CHF 90" -> 90, "$1,200" -> 1200,
    "4.2" -> 42, the same over-match the text scan accepts). A
    numeric ``never_disclose`` item compares against these so a
    listed amount inside a verbatim quote still matches."""
    amounts = []
    for span in rendered_spans:
        pos = 0
        while True:
            m = _DIGIT_RUN.search(span, pos)
            if m is None:
                break
            text = m.group(0)
            end = m.end()
            while True:
                nxt = _DIGIT_RUN.search(span, end)
                if nxt is None or not all(
                    c in _SEP for c in span[end:nxt.start()]
                ):
                    break
                text += nxt.group(0)
                end = nxt.end()
            amounts.append(Decimal(text))
            pos = end
    return amounts
