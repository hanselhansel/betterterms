"""The quote-amount rule and the rendered-value floor checks
(decision 0016, spec 4.4).

A ``{quote:n}`` placeholder restates something the counterparty
wrote: a numeric entry in the inbound ``amounts`` list renders as
money like any structured value; a string entry renders the words
verbatim and stays visible in ``find.masked``, because inbound.yaml
is written by the agent so those words are the agent's to vouch for
and the review tier reads them like the agent's own text. Either way
a quote is never the agent's own offer, so the worse-than-floor and
unconvertible-period checks never reach it on any action. Equality
with the floor still blocks: a rendered value equal to the walk-away
number leaks it regardless of who wrote it. The rendered text is
still scanned, so a ``never_disclose`` term inside a verbatim quote
blocks like anywhere else.

The floor rules on rendered placeholder values live here too:
``check_values`` applies them to the values ``render.render``
placed, ``converted_match`` and ``floor_digits`` back the review
tier's converted-limit and same-digits reasons. ``floor_in_text``
closes the last gap: structured checks never see text, so the final
rendered message itself is scanned with ``money.find`` and any
amount equal to the floor blocks outright.
"""

import re

from . import FLOOR_TOL, LIMITS, minor, money, render

# Placeholder value kinds whose amount is the agent's own price:
# target, ladder and price options always; fact amounts on an
# agreeing action (on ``send`` a fact restates what was already on
# the table). Quotes are absent by design (spec 4.4).
PRICE_KINDS = ("target", "ladder", "option:price", "fact")


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
            findings.append(("block", LIMITS))
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
    clean pass. A match in the floor's own period already routes to
    the review tier and a non-offer value equal to the floor blocks
    outright, so only the offer needs this check. ``accept``,
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

# The one reason the rendered-text floor check reports: no number,
# so a block output can never carry the floor's own digits.
FLOOR_TEXT = "the message contains your walk-away amount"

# Period words the money parser's ``num per month`` grammar accepts,
# mapped to the periods a floor can convert between. Week, day,
# hour and quarter have no conversion factor, so they map to None
# and the amount still compares as written.
_TEXT_PERIODS = {
    "mo": "month", "month": "month",
    "yr": "year", "year": "year", "annum": "year",
    "week": None, "wk": None, "day": None,
    "hr": None, "hour": None, "quarter": None,
}
_PERIOD_TRAIL = re.compile(
    r"(?:\s*/\s*|\s+(?:a|an|per|each|every)\s+)"
    r"(?P<period>mo|month|yr|year|annum|week|wk|day|hr|hour|quarter)"
    r"s?\b",
    re.IGNORECASE,
)


def _written_period(text, amount):
    """The period an amount states in the text, when it states one:
    inside its own span ("100 a month") or in the connector right
    after it ("$100/month", "$100 per year"), matching the parser's
    own ``num per month`` grammar. A period with no floor conversion
    factor returns None, so the amount still compares as written."""
    m = _PERIOD_TRAIL.search(text[amount.start:amount.end])
    if m is None:
        m = _PERIOD_TRAIL.match(text[amount.end:amount.end + 24])
    if m is None:
        return None
    return _TEXT_PERIODS.get(m.group("period").lower())


def floor_in_text(find, offer, offer_period, floor, plan_period,
                  currency):
    """True when the final rendered text states the floor value.

    Structured checks compare placeholder values only, but fact
    bodies, verbatim string quotes and literal template words all
    reach the wire, so ``find.text`` is scanned with ``money.find``
    and every amount is compared to the floor as written and again
    in the floor's declared period when the text names a convertible
    one ("$100 a month" against a yearly floor).

    The one exemption is the draft's own ``{offer}`` output when the
    offer itself sits at the floor: sending at the walk-away is the
    user's own call to approve, so text matching the exact
    ``money_text`` the renderer produced for the offer never counts.
    A duplicate of that same string elsewhere is indistinguishable
    from the offer's own output and exempts with it; the message
    carries the number once through the offer either way."""
    if find.text is None:
        return False
    exempt = []
    if offer is not None and (
        same(in_floor_period(offer, offer_period, plan_period), (floor,))
        or same(minor(offer), (floor,))
    ):
        lit = render.money_text(offer, offer_period, currency)
        start = 0
        while True:
            i = find.text.find(lit, start)
            if i < 0:
                break
            exempt.append((i, i + len(lit)))
            start = i + 1
    for amount in money.find(find.text):
        if any(s <= amount.start and amount.end <= e for s, e in exempt):
            continue
        if same(minor(amount.value), (floor,)):
            return True
        written = _written_period(find.text, amount)
        if written in ("month", "year") and same(
            in_floor_period(amount.value, written, plan_period), (floor,)
        ):
            return True
    return False
