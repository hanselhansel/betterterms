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
   offer inside the band equal to the draft offer
8. any rendered placeholder value equal to the floor or its x12/x1/12
   conversions -> block, except the in-band offer itself; a price
   value (target, ladder, price option, quote not on ``send``) worse
   than the floor blocks too. Bonus and fee options are not offers,
   so only the equal-to-floor rule reaches them
9. rendered message over 64 KB, checked after fact expansion and
   before any text scanning -> block
10. any claim id (draft or auto-claimed by ``{fact:id}``) not in
    ``plan.facts`` -> block

The review tier never blocks but never passes silently either: a
draft whose rendered text (placeholder outputs masked, fact text
visible) trips a check in ``render.review`` returns
``needs_approval`` with plain-word reasons that carry no numbers.
Anything money-shaped, numeric, committal or invisible in the literal
text, and every ``never_disclose`` term, routes to the user.
Irreversible actions, coach mode and autonomy 1 also need approval.

``block`` dominates ``needs_approval``, which dominates ``pass``, and
every floor-related block reports the same generic reason so the
output can never leak the floor's value, direction or distance.
"""

import math

from . import BtError, cases, render

IRREVERSIBLE = {"accept", "cancel", "pay", "sign", "dispute"}
OFFERED = {"accept", "pay", "sign"}
ACTIONS = IRREVERSIBLE | {"send"}
DRAFT_KEYS = {"action", "offer", "period", "template", "claims"}
FLOOR_TOL = 0.005
LIMITS = "outside your limits; escalate to the user"
MAX_TEXT = 64 * 1024


def _worse(value, floor, direction):
    return value < floor - FLOOR_TOL if direction == "receive" else value > floor + FLOOR_TOL


def _same(a, values):
    return any(abs(a - v) <= FLOOR_TOL for v in values)


def _check_values(find, action, floor, direction, plan_period, findings):
    """Floor rules on the amounts the placeholders placed: every value
    except the offer itself must not equal the floor or its period
    conversions, and a price value (target, ladder, price option,
    quote not on ``send``) must not be worse than the floor. Bonus
    and fee options are not offers, so only the equality rule reaches
    them."""
    equiv = (floor, floor * 12, floor / 12)
    for v in find.values:
        if v.value is None:
            continue
        nv = render.convert(v.value, v.period, plan_period)
        if v.kind != "offer" and (_same(nv, equiv) or _same(v.value, equiv)):
            findings.append(("block", LIMITS))
        elif v.kind in ("target", "ladder", "option:price", "quote") and not (
            v.kind == "quote" and action == "send"
        ) and _worse(nv, floor, direction):
            findings.append(("block", LIMITS))


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

    findings = []  # (kind, message); kind is "block" or "approval"

    extra = sorted(str(k) for k in draft if k not in DRAFT_KEYS)
    if extra:
        findings.append(("block", "unknown draft keys: " + ", ".join(extra)))
    if "text" in draft:
        findings.append(("block", "use template, not text"))

    action = draft.get("action")
    if action not in ACTIONS:
        findings.append(("block", f"draft action {action!r} not one of {sorted(ACTIONS)}"))

    raw_offer = draft.get("offer")
    offer = cases.num(raw_offer)
    if raw_offer is not None and (
        isinstance(raw_offer, bool)
        or not isinstance(raw_offer, (int, float))
        or not math.isfinite(offer)
    ):
        findings.append(("block", "offer must be a number"))
        offer = None

    raw_period = draft.get("period", "once")
    if not isinstance(raw_period, str) or raw_period.lower() not in render.PERIODS:
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
    if in_offer is not None and not math.isfinite(in_offer):
        in_offer = None

    find = render.render(
        template, offer, period, plan, plan_period, in_amounts
    ) if template is not None else None
    clean = find is not None and not find.errors
    if find is not None:
        for reason in find.errors:
            findings.append(("block", reason))
        # The size limit lands on the rendered message (fact expansion
        # included) before any scanning runs.
        if len(find.text.encode("utf-8")) > MAX_TEXT:
            findings.append(("block", "message too large"))
            clean = False

    if action in OFFERED:
        if offer is None:
            findings.append(("block", f"{action} requires an offer"))
        if action == "accept":
            if in_offer is None:
                findings.append(("block", "accept requires the counterparty's offer"))
            elif offer is not None and abs(offer - in_offer) > FLOOR_TOL:
                findings.append(("block", "accept must equal the counterparty's offer"))
            if floor is not None and in_offer is not None and _worse(in_offer, floor, direction):
                findings.append(("block", LIMITS))

    if floor is not None:
        if offer is not None and _worse(
            render.convert(offer, period, plan_period), floor, direction
        ):
            findings.append(("block", LIMITS))
        if clean:
            _check_values(find, action, floor, direction, plan_period, findings)

    fact_ids = {
        str(f["id"])
        for f in cases.as_list(plan.get("facts"))
        if isinstance(f, dict) and f.get("id") is not None
    }
    claims = {str(c) for c in cases.as_list(draft.get("claims"))}
    if find is not None:
        claims |= find.fact_ids
    for c in sorted(claims):
        if c not in fact_ids:
            findings.append(("block", f"claim {c} not in plan facts"))

    if action in IRREVERSIBLE and not approved:
        findings.append(("approval", f"action {action!r} requires --approved"))
    if not approved:
        if mode == "coach":
            findings.append(("approval", "coach mode: the user approves every send"))
        if autonomy == 1:
            findings.append(("approval", "autonomy 1: the user approves every send"))
        if clean:
            for reason in render.review(
                find, floor, cases.as_list(brief.get("never_disclose"))
            ):
                findings.append(("approval", reason))

    reasons = []
    seen = set()
    for _, msg in findings:
        if msg not in seen:
            seen.add(msg)
            reasons.append(msg)
    if any(kind == "block" for kind, _ in findings):
        return "block", reasons, None
    if findings:
        return "needs_approval", reasons, find.text if find else None
    return "pass", reasons, find.text if find else None
