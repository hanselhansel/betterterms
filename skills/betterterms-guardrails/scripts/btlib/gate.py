"""Pre-send gate. ``check(case_dir, draft, approved)`` evaluates the gate
rules in order and returns ``(result, reasons)`` where result is
``"pass"``, ``"block"`` or ``"needs_approval"``.

Rules, in order:
1. missing ``.floor`` -> block
2. irreversible action without ``--approved`` -> needs_approval
3. offer worse than the floor for the case direction -> block
4. floor value in ``text`` under any normalization -> block
5. any ``never_disclose`` string in ``text`` -> block
6. any claim id not in ``plan.facts`` -> block
7. any marked amount in ``text`` that is not the offer, an option or
   ladder value, the target, an amount inside a fact's text, or an
   amount the counterparty itself stated in ``inbound`` (text or offer)
   -> block ("untraced number")

All rules run; block dominates needs_approval, which dominates pass.
"""

from . import BtError, cases, money

IRREVERSIBLE = {"accept", "cancel", "pay", "sign", "dispute"}
ACTIONS = IRREVERSIBLE | {"send"}
FLOOR_TOL = 0.005


def _values(mapping, key):
    out = []
    for item in cases.as_list(mapping):
        if isinstance(item, dict):
            v = cases.num(item.get(key))
            if v is not None:
                out.append(v)
    return out


def check(case_dir, draft, approved=False, inbound=None):
    if not isinstance(draft, dict):
        raise BtError("draft must be a mapping")
    if inbound is not None and not isinstance(inbound, dict):
        raise BtError("inbound must be a mapping")
    brief = cases.load_brief(case_dir)
    plan = cases.load_plan(case_dir)
    floor = cases.read_floor(case_dir)
    direction = str(brief.get("direction") or "pay").lower()
    text = str(draft.get("text") or "")
    offer = cases.num(draft.get("offer"))

    findings = []  # (kind, message); kind is "block" or "approval"

    if floor is None:
        findings.append(("block", "no floor set for case"))

    action = draft.get("action")
    if action not in ACTIONS:
        findings.append(("block", f"draft action {action!r} not one of {sorted(ACTIONS)}"))
    elif action in IRREVERSIBLE and not approved:
        findings.append(("approval", f"action {action!r} requires --approved"))

    if floor is not None and offer is not None:
        if direction == "receive":
            worse = offer < floor - FLOOR_TOL
        else:
            worse = offer > floor + FLOOR_TOL
        if worse:
            findings.append(
                ("block", f"offer {cases.num_repr(offer)} worse than floor for direction {direction}")
            )

    found = money.find(text)
    if floor is not None and any(abs(a.value - floor) <= FLOOR_TOL for a in found):
        findings.append(("block", "floor disclosed in draft text"))

    low = text.lower()
    for item in cases.as_list(brief.get("never_disclose")):
        s = str(item)
        if s and s.lower() in low:
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
    if inbound is not None:
        v = cases.num(inbound.get("offer"))
        if v is not None:
            allowed.append(v)
        allowed += money.amounts(str(inbound.get("text") or ""))

    seen = set()
    for a in found:
        if not a.marked:
            continue
        if any(abs(a.value - v) <= FLOOR_TOL for v in allowed):
            continue
        key = round(a.value, 3)
        if key not in seen:
            seen.add(key)
            findings.append(("block", f"untraced number {cases.num_repr(a.value)} in draft text"))

    if any(kind == "block" for kind, _ in findings):
        result = "block"
    elif findings:
        result = "needs_approval"
    else:
        result = "pass"
    return result, [msg for _, msg in findings]
