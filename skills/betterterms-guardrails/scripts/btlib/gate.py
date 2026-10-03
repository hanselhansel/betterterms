"""Pre-send gate. ``check(case_dir, draft, approved, inbound)`` evaluates
the gate rules and returns ``(result, reasons)`` where result is
``"pass"``, ``"block"`` or ``"needs_approval"``.

The gate fails closed: anything it cannot read or cannot prove safe is a
block, and every floor-related block reports the same generic reason so
the output can never leak the floor's value, direction or distance.

Rules, all evaluated (block dominates needs_approval, which dominates
pass):

1. draft or inbound text over 64 KB -> block "message too long"
2. missing, unreadable or invalid ``.floor`` -> block
3. missing or unknown ``action`` -> block
4. irreversible action without ``--approved`` -> needs_approval
5. coach mode or autonomy 1 without ``--approved`` -> needs_approval
6. ``offer`` present but not a plain number -> block
7. for ``pay`` any marked amount in ``text`` greater than the floor, for
   ``receive`` any marked amount below it -> block, unless every such
   amount appears in the counterparty's inbound text or offer and the
   draft's numeric offer is inside the band (quoting the counterparty)
8. ``offer`` outside the band -> block; ``accept``, ``sign`` and ``pay``
   also require a numeric offer inside the band, and ``accept`` may not
   take an inbound offer that is itself outside the band
9. a number token in ``text`` whose digits equal the floor's (or the
   floor's integer part when the floor has cents), or an amount equal
   to the floor -> block
10. any ``never_disclose`` string, or an amount equal to a numeric
    ``never_disclose`` item, in ``text`` -> block
11. any claim id not in ``plan.facts`` -> block
12. any marked amount in ``text`` that is not the offer, an option or
    ladder value, the target, an amount inside a fact's text, or an
    amount the counterparty itself stated in ``inbound`` (text or
    offer) -> block ("untraced number", reported once, no value)
"""

import math
import re

from . import BtError, cases, money

IRREVERSIBLE = {"accept", "cancel", "pay", "sign", "dispute"}
OFFERED = {"accept", "pay", "sign"}
ACTIONS = IRREVERSIBLE | {"send"}
FLOOR_TOL = 0.005
LIMITS = "outside your limits; escalate to the user"
MAX_TEXT = 64 * 1024

# Rule 9's floor scan reads number tokens, not substrings: a token is a
# digit run where group separators (comma, period, apostrophe, a single
# regular or thin space) appear only before 3-digit groups, so "11,200"
# or "312005" are one token while "1 200", "1.200" and "1'200" all read
# as 1200. Only an exact digit match blocks.
_NUM_TOKEN = re.compile(
    r"\d{1,3}(?:[,.' \u00a0\u2007-\u200a\u202f]\d{3}(?!\d))+"
    r"|\d+"
)


def _values(mapping, key):
    out = []
    for item in cases.as_list(mapping):
        if isinstance(item, dict):
            v = cases.num(item.get(key))
            if v is not None:
                out.append(v)
    return out


def _worse(value, floor, direction):
    return value < floor - FLOOR_TOL if direction == "receive" else value > floor + FLOOR_TOL


def _same(a, values):
    return any(abs(a - v) <= FLOOR_TOL for v in values)


def check(case_dir, draft, approved=False, inbound=None):
    if not isinstance(draft, dict):
        raise BtError("draft must be a mapping")
    if inbound is not None and not isinstance(inbound, dict):
        raise BtError("inbound must be a mapping")
    brief = cases.load_brief(case_dir)
    plan = cases.load_plan(case_dir)
    direction = cases.direction_of(brief)
    floor = cases.read_floor(case_dir)
    cases.check_plan_limits(plan, floor, direction)

    text = str(draft.get("text") or "")
    inbound_text = str((inbound or {}).get("text") or "")
    findings = []  # (kind, message); kind is "block" or "approval"

    if len(text.encode("utf-8")) > MAX_TEXT or len(inbound_text.encode("utf-8")) > MAX_TEXT:
        findings.append(("block", "message too long"))

    if floor is None:
        findings.append(("block", LIMITS))

    action = draft.get("action")
    if action not in ACTIONS:
        findings.append(("block", f"draft action {action!r} not one of {sorted(ACTIONS)}"))
    elif action in IRREVERSIBLE and not approved:
        findings.append(("approval", f"action {action!r} requires --approved"))

    if not approved:
        if brief.get("mode") == "coach":
            findings.append(("approval", "coach mode: the user approves every send"))
        if cases.num(brief.get("autonomy")) == 1:
            findings.append(("approval", "autonomy 1: the user approves every send"))

    # The floor rule can only compare a plain number; anything else is a
    # block, never a silent skip.
    raw_offer = draft.get("offer")
    offer = cases.num(raw_offer)
    if raw_offer is not None and (
        isinstance(raw_offer, bool)
        or not isinstance(raw_offer, (int, float))
        or not math.isfinite(offer)
    ):
        findings.append(("block", "offer must be a number"))
        offer = None

    in_offer = cases.num(inbound.get("offer")) if inbound else None
    if in_offer is not None and not math.isfinite(in_offer):
        in_offer = None

    found = money.find(text)
    in_amounts = set()
    if inbound is not None:
        in_amounts = {a.value for a in money.find(inbound_text)}
        if in_offer is not None:
            in_amounts.add(in_offer)

    if floor is not None:
        floor_repr = cases.num_repr(floor)
        leaked = {re.sub(r"\D", "", floor_repr)}
        if floor >= 1 and not floor.is_integer():
            leaked.add(str(int(floor)))
        if any(
            re.sub(r"\D", "", m.group(0)) in leaked
            for m in _NUM_TOKEN.finditer(text)
        ):
            findings.append(("block", LIMITS))
        if any(abs(a.value - floor) <= FLOOR_TOL for a in found):
            findings.append(("block", LIMITS))

        crossed = [
            a.value for a in found
            if a.marked and _worse(a.value, floor, direction)
        ]
        if crossed:
            quoted = offer is not None and not _worse(offer, floor, direction) and all(
                _same(v, in_amounts) for v in crossed
            )
            if not quoted:
                findings.append(("block", LIMITS))

        if offer is not None and _worse(offer, floor, direction):
            findings.append(("block", LIMITS))

        if action in OFFERED:
            if offer is None or _worse(offer, floor, direction):
                findings.append(("block", LIMITS))
            elif action == "accept" and in_offer is not None and _worse(in_offer, floor, direction):
                findings.append(("block", LIMITS))

    low = text.lower()
    nd_hit = False
    for item in cases.as_list(brief.get("never_disclose")):
        s = str(item)
        if s and s.lower() in low:
            nd_hit = True
            continue
        for v in money.amounts(s):
            if _same(v, [a.value for a in found]):
                nd_hit = True
                break
    if nd_hit:
        findings.append(("block", "never-disclose term appears in draft text"))

    fact_ids = set()
    allowed = []
    for f in cases.as_list(plan.get("facts")):
        if isinstance(f, dict):
            if f.get("id") is not None:
                fact_ids.add(str(f["id"]))
            if f.get("text") is not None:
                allowed += money.amounts(str(f["text"]))
    for claim in cases.as_list(draft.get("claims")):
        if str(claim) not in fact_ids:
            findings.append(("block", f"claim {claim} not in plan facts"))

    for v in (offer, cases.num(plan.get("target"))):
        if v is not None:
            allowed.append(v)
    allowed += _values(plan.get("options"), "value")
    allowed += _values(plan.get("ladder"), "value")
    allowed += in_amounts

    if any(a.marked and not _same(a.value, allowed) for a in found):
        findings.append(("block", "untraced number in draft text"))

    reasons = []
    seen = set()
    for _, msg in findings:
        if msg not in seen:
            seen.add(msg)
            reasons.append(msg)
    if any(kind == "block" for kind, _ in findings):
        result = "block"
    elif findings:
        result = "needs_approval"
    else:
        result = "pass"
    return result, reasons
