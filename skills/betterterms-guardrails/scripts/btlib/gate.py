"""Pre-send gate. ``check(case_dir, draft, approved, inbound)`` returns
``(result, reasons, rendered)`` where result is ``"pass"``, ``"block"``
or ``"needs_approval"`` and rendered is the final message text the
agent must send verbatim (None on block).

The gate has two tiers (decision 0009). Hard blocks are code
guarantees and fail closed:

1. invalid brief (direction, mode, autonomy) or conflicting plan ->
   error, exit 2
2. missing, unreadable or invalid ``.floor`` -> block
3. missing or unknown ``action`` -> block
4. unknown draft keys or a legacy ``text`` key -> block
5. ``offer`` present but not a plain number, or ``period`` outside
   once|month|year, or template not a string -> block
6. unknown, malformed or unresolvable placeholder -> block, naming
   the placeholder
7. offer worse than the floor, compared in the floor's declared
   period -> block; ``accept``, ``sign`` and ``pay`` also require a
   numeric offer inside the band, and ``accept`` requires an inbound
   offer inside the band equal to the draft offer, both read in the
   floor's period. ``once`` has no conversion factor, so a period
   mismatch where either side is ``once`` can never be verified:
   ``send`` routes to the user (``period differs from your limit``),
   the agreeing actions block, and the same rule covers the inbound
   offer's period on ``accept``
8. any rendered placeholder value equal to the floor -> block,
   except the in-band offer itself; a value equal only to the
   floor's x12 or /12 conversion is a review hit (``amount matches
   a converted limit``, no numbers). A ``send`` offer equal to the
   floor after conversion is a review hit too (``offer is at your
   limit``): inside the band, but it reveals the walk-away number;
   ``accept``, ``sign`` and ``pay`` may sit exactly on it. A price
   value (target, ladder, price option, quote or fact amount not on
   ``send``) worse than the floor blocks too, and a price value
   whose period cannot convert to the floor's fails closed like an
   unconvertible offer; fact values read the structured ``amount``
   field only, never the text (decision 0010). A ``send`` may
   render a quote or fact worse than the floor: restating a price
   the counterparty named is not the agent's offer. Bonus and fee
   options are not offers, so only the equal-to-floor rule reaches
   them
9. rendered message over 64 KB, checked after fact expansion and
   before any text scanning -> block
10. any claim id (draft or auto-claimed by ``{fact:id}``) not in
    ``plan.facts`` -> block

The review tier never blocks but never passes silently either: a
draft whose rendered text (placeholder outputs masked, fact text
visible) trips a check in ``btlib.review`` returns
``needs_approval`` with plain-word reasons that carry no numbers.
The text scan is an allowlist (decisions 0009 amendment, 0010):
characters off the permitted set, any ASCII digit anywhere, any
number word inside a letter run outside the listed exceptions,
currency or scale words and codes, listed commitment words and
phrases, sentinel glue and every ``never_disclose`` term all route
to the user; numeric ``never_disclose`` items also compare against
the rendered placeholder values. A ``send`` offer whose digits equal
the floor's digits in a different period routes too (``amount
matches your limit's digits``): the converted value clears the band
but the digits still restate the walk-away number. Irreversible
actions, coach mode, autonomy 1 and a ``send`` offer at the floor
also need approval.

``block`` dominates ``needs_approval``, which dominates ``pass``, and
every floor-related block reports the same generic reason so the
output can never leak the floor's value, direction or distance.
"""

from . import BtError, FLOOR_TOL, PERIODS, cases, minor, render, review

IRREVERSIBLE = {"accept", "cancel", "pay", "sign", "dispute"}
OFFERED = {"accept", "pay", "sign"}
ACTIONS = IRREVERSIBLE | {"send"}
DRAFT_KEYS = {"action", "offer", "period", "template", "claims"}
LIMITS = "outside your limits; escalate to the user"
PRICE_KINDS = ("target", "ladder", "option:price", "quote", "fact")

# A block never reports the converted-limit or same-digits review
# hits: on a block they would each leak one bit about the floor, so
# only the generic limit reason (and any structural blocks) reports.
DROP_ON_BLOCK = {
    "amount matches a converted limit",
    "amount matches your limit's digits",
}


def _safe_str(value):
    """``str()`` that cannot raise: a value whose conversion fails
    (an int past the int-to-str digit limit) becomes a type tag, so
    it can only fail a comparison, never turn a block into a crash."""
    try:
        return str(value)
    except Exception:
        return f"<{type(value).__name__}>"


def _shown(value):
    """A draft value as a block reason reports it, capped short so a
    hostile scalar cannot blow up either the conversion or the reason
    itself."""
    s = _safe_str(value)
    return s if len(s) <= 40 else s[:40] + "..."


def _worse(value, floor, direction):
    return value < floor - FLOOR_TOL if direction == "receive" else value > floor + FLOOR_TOL


def _same(a, values):
    return any(abs(a - v) <= FLOOR_TOL for v in values)


def _in_floor_period(value, from_period, plan_period):
    """``value`` as it renders (minor unit), converted and rounded
    again: comparisons always read rendered amounts."""
    return minor(render.convert(minor(value), from_period, plan_period))


def _check_values(find, action, floor, direction, plan_period, findings):
    """Floor rules on the amounts the placeholders placed: every value
    except the offer itself must not equal the floor (in its own or
    the floor's period), and a price value (target, ladder, price
    option, quote or fact amount not on ``send``) must not be worse
    than the floor. Fact amounts come from the structured ``amount``
    field only, never parsed text (decision 0010). Equality with only
    a period conversion is a review hit, not a block; it is checked
    in ``_converted_match`` under the review tier. Bonus and fee
    options are not offers, so only the equality rule reaches them.
    A price value whose period cannot convert to the floor's (``once``
    on either side) fails closed like an unconvertible offer."""
    for v in find.values:
        quoted = v.kind in ("quote", "fact") and action == "send"
        priced = v.kind in PRICE_KINDS and not quoted
        if priced and v.period != plan_period and "once" in (
            v.period, plan_period
        ):
            findings.append(("block", "period differs from your limit"))
            continue
        nv = _in_floor_period(v.value, v.period, plan_period)
        if v.kind != "offer" and (
            _same(nv, (floor,)) or _same(minor(v.value), (floor,))
        ):
            findings.append(("block", LIMITS))
        elif priced and _worse(nv, floor, direction):
            findings.append(("block", LIMITS))


def _converted_match(find, floor, plan_period):
    """True when a rendered non-offer value equals the floor's x12 or
    /12 conversion in its own or the floor's period, without equalling
    the floor itself: "5/year" against a 60/month floor is a numeric
    coincidence the user must see, not proof of a leak."""
    for v in find.values:
        if v.kind == "offer":
            continue
        nv = _in_floor_period(v.value, v.period, plan_period)
        for val in (nv, minor(v.value)):
            if _same(val, (floor * 12, floor / 12)) and not _same(
                val, (floor,)
            ):
                return True
    return False


def _floor_digits(find, floor, plan_period, action):
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
        nv = _in_floor_period(v.value, v.period, plan_period)
        if _same(minor(v.value), (floor,)) and not _same(nv, (floor,)):
            return True
    return False


def check(case_dir, draft, approved=False, inbound=None):
    if not isinstance(draft, dict):
        raise BtError("draft must be a mapping")
    if inbound is not None and not isinstance(inbound, dict):
        raise BtError("inbound must be a mapping")
    brief = cases.load_brief(case_dir)
    plan = cases.load_plan(case_dir)
    direction = cases.direction_of(brief)
    mode = cases.mode_of(brief)
    autonomy = cases.autonomy_of(brief)
    floor = cases.read_floor(case_dir)
    cases.check_plan_limits(plan, floor, direction, brief)
    plan_period = cases.floor_period(plan, brief)
    currency = cases.currency_of(plan, brief)

    findings = []  # (kind, message); kind is "block" or "approval"

    extra = sorted(_shown(k) for k in draft if k not in DRAFT_KEYS)
    if extra:
        findings.append(("block", "unknown draft keys: " + ", ".join(extra)))
    if "text" in draft:
        findings.append(("block", "use template, not text"))

    action = draft.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        findings.append(("block", f"draft action {_shown(action)!r} not one of {sorted(ACTIONS)}"))
        action = None

    raw_offer = draft.get("offer")
    offer = cases.num(raw_offer)
    if raw_offer is not None and (
        isinstance(raw_offer, bool)
        or not isinstance(raw_offer, (int, float))
        or offer is None
    ):
        findings.append(("block", "offer must be a number"))
        offer = None

    # A null draft period means "not set" and defaults to once, like
    # the plan, fact and inbound period keys.
    raw_period = draft.get("period")
    if raw_period is None:
        period = "once"
    elif not isinstance(raw_period, str) or raw_period.lower() not in PERIODS:
        findings.append(("block", "period must be once, month or year"))
        period = "once"
    else:
        period = raw_period.lower()

    template = draft.get("template")
    if not isinstance(template, str):
        findings.append(("block", "template must be a string"))
        template = None

    if floor is None:
        findings.append(("block", LIMITS))

    in_amounts = cases.as_list(inbound.get("amounts")) if inbound else []
    in_offer = cases.num(inbound.get("offer")) if inbound else None
    # An inbound offer is read in its own period when the inbound
    # declares one, else in the floor's period; either way it is
    # converted to the floor's period before any comparison.
    in_period = plan_period
    if inbound and inbound.get("period") is not None:
        raw_in = inbound.get("period")
        if not isinstance(raw_in, str) or raw_in.lower() not in PERIODS:
            findings.append(("block", "period must be once, month or year"))
        else:
            in_period = raw_in.lower()

    find = render.render(
        template, offer, period, plan, plan_period, in_amounts, currency
    ) if template is not None else None
    clean = find is not None and not find.errors
    if find is not None:
        for reason in find.errors:
            findings.append(("block", reason))
        # The size limit lands on the rendered message (fact expansion
        # included) before any scanning runs; render sums piece lengths
        # and never joins the oversized string.
        if find.oversized:
            findings.append(("block", "message too large"))
            clean = False

    if action in OFFERED:
        if offer is None:
            findings.append(("block", f"{action} requires an offer"))
        if action == "accept":
            if in_offer is None:
                findings.append(("block", "accept requires the counterparty's offer"))
            else:
                # The inbound offer's period must match or convert
                # like the draft's; a once mix fails closed.
                if in_period != plan_period and "once" in (
                    in_period, plan_period
                ):
                    findings.append(
                        ("block", "period differs from your limit")
                    )
                in_floor = _in_floor_period(
                    in_offer, in_period, plan_period
                )
                if offer is not None and not _same(
                    _in_floor_period(offer, period, plan_period),
                    (in_floor,),
                ):
                    findings.append(("block", "accept must equal the counterparty's offer"))
                if floor is not None and _worse(in_floor, floor, direction):
                    findings.append(("block", LIMITS))

    if floor is not None:
        if offer is not None:
            offer_floor = _in_floor_period(offer, period, plan_period)
            # "once" has no conversion factor, so a period mismatch
            # with it can never verify the offer against the floor:
            # the raw values are unlike units, so the worse-than and
            # at-limit comparisons are skipped entirely. A send routes
            # to the user, an agreeing action fails closed.
            unconvertible = (
                period != plan_period
                and "once" in (period, plan_period)
            )
            if unconvertible:
                if action == "send":
                    if not approved:
                        findings.append(
                            ("approval", "period differs from your limit")
                        )
                else:
                    findings.append(
                        ("block", "period differs from your limit")
                    )
            elif _worse(offer_floor, floor, direction):
                findings.append(("block", LIMITS))
            elif (
                not approved
                and action == "send"
                and _same(offer_floor, (floor,))
            ):
                # A send offer at the floor is inside the band, but it
                # hands the counterparty the user's walk-away number.
                # accept, sign and pay may sit on it: they take a price
                # already on the table.
                findings.append(("approval", "offer is at your limit"))
        if clean:
            _check_values(find, action, floor, direction, plan_period, findings)

    fact_ids = {
        _safe_str(f["id"])
        for f in cases.as_list(plan.get("facts"))
        if isinstance(f, dict) and f.get("id") is not None
    }
    claims = {_safe_str(c) for c in cases.as_list(draft.get("claims"))}
    if find is not None:
        claims |= find.fact_ids
    for c in sorted(claims):
        if c not in fact_ids:
            findings.append(("block", f"claim {_shown(c)} not in plan facts"))

    if action in IRREVERSIBLE and not approved:
        findings.append(("approval", f"action {action!r} requires --approved"))
    if not approved:
        if mode == "coach":
            findings.append(("approval", "coach mode: the user approves every send"))
        if autonomy == 1:
            findings.append(("approval", "autonomy 1: the user approves every send"))
        if clean:
            for reason in review.review(
                find, cases.as_list(brief.get("never_disclose"))
            ):
                findings.append(("approval", reason))
            if floor is not None:
                if _converted_match(find, floor, plan_period):
                    findings.append(
                        ("approval", "amount matches a converted limit")
                    )
                if _floor_digits(find, floor, plan_period, action):
                    findings.append(
                        ("approval", "amount matches your limit's digits")
                    )

    blocked = any(kind == "block" for kind, _ in findings)
    reasons = []
    seen = set()
    for _, msg in findings:
        if blocked and msg in DROP_ON_BLOCK:
            continue
        if msg not in seen:
            seen.add(msg)
            reasons.append(msg)
    if blocked:
        return "block", reasons, None
    if findings:
        return "needs_approval", reasons, find.text if find else None
    return "pass", reasons, find.text if find else None
