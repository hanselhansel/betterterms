"""Pre-send gate. ``check(case_dir, draft, approved, inbound)`` returns
``(result, reasons, rendered)`` where result is ``"pass"``, ``"block"``
or ``"needs_approval"`` and rendered is the final message text the
agent must send verbatim (None on block).

Drafts are structured: ``action``, ``offer`` (a plain number or null),
``period`` (once|month|year), ``template`` (message text with
placeholders) and ``claims`` (fact ids). Prices reach the message only
through placeholders, rendered by ``render.render``; literal free text
may not contain anything money-shaped. The gate fails closed, and every
floor-related block reports the same generic reason so the output can
never leak the floor's value, direction or distance.

Rules, all evaluated (block dominates needs_approval, which dominates
pass):

1. unknown draft keys, a ``text`` key, or a non-mapping draft -> block
2. template missing, not a string or over 64 KB -> block
3. missing, unreadable or invalid ``.floor`` -> block
4. missing or unknown ``action`` -> block
5. ``offer`` present but not a plain number, or ``period`` outside
   once|month|year -> block
6. unknown or unresolvable placeholder -> block, naming the placeholder
7. offer worse than the floor (after period conversion) -> block;
   ``accept``, ``sign`` and ``pay`` also require a numeric offer inside
   the band, and ``accept`` requires an inbound offer inside the band
   equal to the draft offer
8. any rendered amount worse than the floor, or equal to the floor's
   value, x12 or /12 -> block, except the in-band offer itself and
   bonus/fee options; a ``{quote:n}`` worse than the floor is allowed
   only on ``send`` (quoting, not agreeing)
9. literal free text containing a currency mark, code, money or scale
   word, a 3+ digit run, separator-joined digits, a number-word run,
   non-ASCII digits, or a small integer equal to the floor or a
   rendered amount -> block
10. any ``never_disclose`` string in the rendered text -> block
11. any claim id (draft or auto-claimed by ``{fact:id}``) not in
    ``plan.facts`` -> block
12. irreversible action without ``--approved``, coach mode, autonomy 1,
    or agreement wording in a ``send`` -> needs_approval
"""

import math

from . import BtError, cases, money, render

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
    """Floor rules on the amounts the placeholders placed: worse than
    the floor, or equal to the floor in any period conversion."""
    equiv = (floor, floor * 12, floor / 12)
    for v in find.values:
        if v.value is None:
            continue
        if v.kind == "offer" or v.kind.startswith("option:") and v.kind != "option:price":
            continue
        nv = render.convert(v.value, v.period, plan_period)
        if _same(nv, equiv) or _same(v.value, equiv):
            findings.append(("block", LIMITS))
        elif v.kind != "fact" and not (v.kind == "quote" and action == "send"):
            if _worse(nv, floor, direction):
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
    cases.check_plan_limits(plan, floor, direction)
    plan_period = cases.plan_period(plan)

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
    elif len(template.encode("utf-8")) > MAX_TEXT:
        findings.append(("block", "template too large"))
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
    if find is not None:
        for reason in find.errors:
            findings.append(("block", reason))

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
        if find is not None and not find.errors:
            _check_values(find, action, floor, direction, plan_period, findings)
            floor_ints = {int(floor), int(floor * 12), int(floor / 12)}
            amount_ints = {
                int(v.value) for v in find.values if v.value is not None
            }
            for v in (offer, in_offer):
                if v is not None:
                    amount_ints.add(int(v))
            hit = render.scan_free_text(find.literal, floor_ints, amount_ints)
            if hit:
                reason, floor_related = hit
                findings.append(("block", LIMITS if floor_related else reason))

    if find is not None and not find.errors:
        low = find.text.lower()
        found_amounts = [a.value for a in money.find(find.text)]
        nd_hit = False
        for item in cases.as_list(brief.get("never_disclose")):
            s = str(item)
            if s and s.lower() in low:
                nd_hit = True
                continue
            if any(_same(v, found_amounts) for v in money.amounts(s)):
                nd_hit = True
        if nd_hit:
            findings.append(("block", "never-disclose term appears in draft text"))

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
        if action == "send" and find is not None and not find.errors:
            word = render.agreement_word(find.literal)
            if word:
                findings.append(("approval", f"agreement wording {word!r}: needs approval"))

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
