"""Pre-send gate. ``check(case_dir, draft, approved, inbound)`` returns
``(result, reasons, rendered)`` where result is ``"pass"``, ``"block"``
or ``"needs_approval"`` and rendered is the final message text the
agent must send verbatim (None on block).

The gate has two tiers (decision 0009). Hard blocks are code
guarantees and fail closed:

1. invalid brief (direction, mode, autonomy) or a conflicting
   plan, or a ``period`` or ``floor_period`` key present but not a
   string naming a known period (a null is a broken key, not a
   default), even shadowed -> error, exit 2. On inbound.yaml an
   explicit ``period: null`` means "not stated" and defaults like
   an absent key; only a present non-null value can be broken
2. missing, unreadable or invalid ``.floor`` -> block
3. missing or unknown ``action``, unknown draft keys or a legacy
   ``text`` key -> block
4. ``offer`` or an inbound ``offer``/``amounts`` entry present but
   not a positive number, ``period`` outside once|month|year, or
   template not a string -> block
5. unknown, malformed or unresolvable placeholder -> block, naming
   the placeholder
6. offer worse than the floor, compared in the floor's declared
   period -> block; ``accept``, ``sign`` and ``pay`` also require a
   numeric offer inside the band, and ``accept`` requires an inbound
   offer inside the band equal to the draft offer, both read in the
   floor's period. ``once`` has no conversion factor, so a period
   mismatch where either side is ``once`` can never be verified:
   ``send`` routes to the user (``period differs from your limit``),
   the agreeing actions block, and the same rule covers the inbound
   offer's period on ``accept``
7. any rendered placeholder value equal to the floor -> block,
   except the in-band offer itself; a value equal only to the
   floor's x12 or /12 conversion is a review hit (``amount matches
   a converted limit``, no numbers). A ``send`` offer equal to the
   floor after conversion is a review hit too (``offer is at your
   limit``): inside the band, but it reveals the walk-away number;
   ``accept``, ``sign`` and ``pay`` may sit exactly on it. A price
   value (target, ladder, price option, or fact amount not on
   ``send``) worse than the floor blocks too, and a price value
   whose period cannot convert to the floor's fails closed like an
   unconvertible offer; fact values read the structured ``amount``
   field only, never the text (decision 0010). A ``send`` may
   render a fact worse than the floor: restating a price the
   counterparty named is not the agent's offer. A quote never meets
   the worse-than or unconvertible-period check on any action
   (spec 4.4): the counterparty's own words or numbers are never
   the agent's offer, and a string ``amounts`` entry renders
   verbatim. Bonus and fee options are not offers, so only the
   equal-to-floor rule reaches them. The final rendered text is
   scanned too: any amount the money parser reads out of it equal
   to the floor, as written or in the floor's declared period,
   blocks with ``the message contains your walk-away amount``; the
   draft's own ``{offer}`` output is exempt when the offer itself
   sits at the floor
8. rendered message over 64 KB, checked after fact expansion and
   before any text scanning, or a claim id (draft or auto-claimed
   by ``{fact:id}``) not in ``plan.facts`` -> block
9. a ``never_disclose`` item with letters anywhere in the rendered
   text, verbatim quote text included -> block: a listed term is
   never a coincidence, so it is not a review item

The review tier never blocks but never passes silently either: a
draft whose rendered text (placeholder outputs masked, fact text
and verbatim string quotes visible: inbound.yaml is agent-written,
so a quoted string is reviewed like the agent's own words) trips a
check in ``btlib.review`` returns
``needs_approval`` with plain-word reasons that carry no numbers.
The text scan is an allowlist (decisions 0009 amendment, 0010):
characters off the permitted set, any ASCII digit anywhere, any
number word inside a letter run outside the listed exceptions,
currency or scale words and codes, listed commitment words and
phrases, sentinel glue and every ``never_disclose`` term all route
to the user; numeric ``never_disclose`` items also compare against
the rendered placeholder values.
A ``send`` offer whose digits equal
the floor's digits in a different period routes too (``amount
matches your limit's digits``): the converted value clears the band
but the digits still restate the walk-away number. Irreversible
actions, coach mode, autonomy 1 and a ``send`` offer at the floor
also need approval.

``block`` dominates ``needs_approval``, which dominates ``pass``, and
every floor-related block reports the same generic reason so the
output can never leak the floor's value, direction or distance.

A ``needs_approval`` draft is held on disk (``held/<sha256>.yaml``,
``btlib.held``) so a user approval can bind to the exact rendered
text. ``approved=True`` no longer skips the review tier by itself: it
only passes when a matching ``held/<sha256>.approved`` file exists,
and consumes it once. Without one the draft is held again with the
reason ``no approval recorded for this exact text``.
"""

from . import (
    BtError, LIMITS, PERIODS, cases, held, quotes, render, review,
)

IRREVERSIBLE = {"accept", "cancel", "pay", "sign", "dispute"}
OFFERED = {"accept", "pay", "sign"}
ACTIONS = IRREVERSIBLE | {"send"}
DRAFT_KEYS = {"action", "offer", "period", "template", "claims"}

# A block reports only the block findings: the at-limit,
# converted-limit or same-digits review hits would each leak one bit
# about the floor, and any other approval finding is noise on a draft
# that cannot be sent at all.


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
    elif offer is not None and offer <= 0:
        findings.append(("block", "offer must be a positive number"))
        offer = None

    # A null draft period means "not set" and defaults to once, and
    # inbound.yaml follows the same rule (the agent writes it from a
    # message that often states no period); the plan-side period keys
    # are stricter and fail on a present null as a broken file
    # (exit 2).
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
    if inbound is not None:
        if in_offer is not None and in_offer <= 0:
            findings.append(
                ("block", "inbound offer must be a positive number")
            )
            in_offer = None
        if any(
            (n := cases.num(a)) is not None and n <= 0
            for a in in_amounts
        ):
            findings.append(
                ("block", "inbound amounts must be positive numbers")
            )
    # An inbound offer is read in its own period when the inbound
    # declares one, else in the floor's period; either way it is
    # converted to the floor's period before any comparison.
    in_period = plan_period
    if inbound:
        raw_in = inbound.get("period")
        # A present non-null inbound period naming no known period is
        # a broken input file like a bad plan period: exit 2, same as
        # the score path, never a negotiation block.
        if raw_in is not None:
            if not isinstance(raw_in, str) or raw_in.lower() not in PERIODS:
                raise BtError(
                    cases.period_error("inbound.yaml period", raw_in)
                )
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
                in_floor = quotes.in_floor_period(
                    in_offer, in_period, plan_period
                )
                if offer is not None and not quotes.same(
                    quotes.in_floor_period(offer, period, plan_period),
                    (in_floor,),
                ):
                    findings.append(("block", "accept must equal the counterparty's offer"))
                if floor is not None and quotes.worse(in_floor, floor, direction):
                    findings.append(("block", LIMITS))

    if floor is not None:
        if offer is not None:
            offer_floor = quotes.in_floor_period(offer, period, plan_period)
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
                    findings.append(
                        ("approval", "period differs from your limit")
                    )
                else:
                    findings.append(
                        ("block", "period differs from your limit")
                    )
            elif quotes.worse(offer_floor, floor, direction):
                findings.append(("block", LIMITS))
            elif (
                action == "send"
                and quotes.same(offer_floor, (floor,))
            ):
                # A send offer at the floor is inside the band, but it
                # hands the counterparty the user's walk-away number.
                # accept, sign and pay may sit on it: they take a price
                # already on the table.
                findings.append(("approval", "offer is at your limit"))
        if clean:
            quotes.check_values(
                find, action, floor, direction, plan_period, findings
            )
            # The structured checks compare placeholder values only;
            # the final text is scanned too, so a floor figure inside
            # fact text, a verbatim string quote or literal words
            # blocks like a leaked limit. A structured value already
            # equal to the floor reports the generic reason, so the
            # plain text reason stays quiet beside it.
            if quotes.floor_in_text(
                find, offer, period, floor, plan_period, currency
            ) and not any(
                kind == "block" and msg == LIMITS
                for kind, msg in findings
            ):
                findings.append(("block", quotes.FLOOR_TEXT))
    never_items = cases.as_list(brief.get("never_disclose"))
    if clean and review.disclosed(find.text, never_items):
        findings.append(
            ("block", "a term from your never-disclose list")
        )

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

    if action in IRREVERSIBLE:
        findings.append(("approval", f"action {action!r} requires --approved"))
    if mode == "coach":
        findings.append(("approval", "coach mode: the user approves every send"))
    if autonomy == 1:
        findings.append(("approval", "autonomy 1: the user approves every send"))
    if clean:
        for reason in review.review(find, never_items):
            findings.append(("approval", reason))
        if floor is not None:
            if quotes.converted_match(find, floor, plan_period):
                findings.append(
                    ("approval", "amount matches a converted limit")
                )
            if quotes.floor_digits(find, floor, plan_period, action):
                findings.append(
                    ("approval", "amount matches your limit's digits")
                )

    blocked = any(kind == "block" for kind, _ in findings)
    reasons = []
    seen = set()
    for kind, msg in findings:
        if blocked and kind != "block":
            continue
        if msg not in seen:
            seen.add(msg)
            reasons.append(msg)
    if blocked:
        return "block", reasons, None
    rendered = find.text if find else None
    if not findings:
        if approved and rendered is not None:
            held.consume_approval(case_dir, rendered)
        return "pass", reasons, rendered
    if (
        approved
        and rendered is not None
        and held.consume_approval(case_dir, rendered)
    ):
        return "pass", [], rendered
    if rendered is not None:
        held.hold(case_dir, rendered, reasons)
    if approved:
        reasons.append(held.NO_APPROVAL)
    return "needs_approval", reasons, rendered
