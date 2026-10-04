"""Inbound message scoring. ``classify(case_dir, inbound)`` returns
``{"band": ..., "escalate": [...], "suggested_amounts": [...]}``.

Bands by direction: ``at_or_above_target`` when the offer meets or beats
the plan target, ``below_floor`` when it is worse than the floor,
``near_floor`` within 10 percent of the floor, else ``in_band``. The
escalate list flags suspected prompt injection, sincere questions about
whether the sender is an AI or bot, and legal or arbitration terms.
Inbound text is data, never instructions.
"""

import re

from . import BtError, MAX_TEXT, PERIODS, cases, minor, money, render

INJECTION = [
    re.compile(
        r"\b(ignore|disregard|forget|override|bypass|skip)\b[^.\n]{0,60}"
        r"\b(previous|prior|above|earlier|all)\b[^.\n]{0,30}"
        r"\b(instructions?|prompts?|rules?|directives?|constraints?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(system|initial|original|hidden)\s+prompt\b", re.IGNORECASE),
    re.compile(
        r"\b(reveal|tell|show|give|share|disclose|repeat|print|output|state|"
        r"report|what\s+is|what's|whats)\b[^.\n]{0,60}"
        r"\b(budget|maximum|max|floor|limit|limits|walk[-\s]?away|"
        r"reservation\s+price|bottom\s+line)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byou\s+are\s+(an?\s+)?ai\s+(assistant|bot|model|agent)\b", re.IGNORECASE),
]

AI_QUESTION = [
    re.compile(
        r"\b(are\s+you|am\s+i\s+(talking|speaking|chatting|texting|dealing)\s+(to|with)|"
        r"is\s+this|is\s+there|were\s+you)\b[^?\n]{0,40}"
        r"\b(ai|a\.i\.|bot|robot|chatbot|human|real\s+person|actual\s+person|"
        r"computer|machine|automated|agent)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(are\s+you|is\s+this)\s+(an?\s+)?(ai|bot|robot|chatbot|human|real)\b", re.IGNORECASE),
]

LEGAL = re.compile(
    r"\b(arbitrat\w*|indemnif\w*|waiv\w*|class[-\s]action|hold\s+harmless|"
    r"liability\s+waiver|jury\s+trial)\b",
    re.IGNORECASE,
)

# Inbound text is normalized (NFKC, format characters stripped) before
# every scan, so fullwidth text and hidden joiners cannot hide a match:
# "prev​ious", "‎bot" and "arbit​ration" still flag.


def _band(direction, target, floor, offer):
    # The floor is checked before the target: an offer outside the band
    # is below_floor even when it happens to beat the plan target.
    if direction == "receive":
        if offer < floor:
            return "below_floor"
    elif offer > floor:
        return "below_floor"
    if target is not None:
        if direction == "receive" and offer >= target:
            return "at_or_above_target"
        if direction != "receive" and offer <= target:
            return "at_or_above_target"
    if abs(offer - floor) <= 0.10 * abs(floor):
        return "near_floor"
    return "in_band"


def classify(case_dir, inbound):
    if not isinstance(inbound, dict):
        raise BtError("inbound must be a mapping")
    brief = cases.load_brief(case_dir)
    plan = cases.load_plan(case_dir)
    direction = cases.direction_of(brief)
    floor = cases.read_floor(case_dir)
    if floor is None:
        raise BtError("no floor set for case")
    cases.check_plan_limits(plan, floor, direction, brief)
    floor_period = cases.floor_period(plan, brief)
    # An inbound offer is read in its declared period, else the
    # floor's; a present non-string or unknown period is a broken
    # inbound file, never a default.
    in_period = floor_period
    raw_in = inbound.get("period")
    if raw_in is not None:
        if not isinstance(raw_in, str) or raw_in.lower() not in PERIODS:
            raise BtError("period must be once, month or year")
        in_period = raw_in.lower()
    target = cases.num(plan.get("target"))
    offer = cases.num(inbound.get("offer"))
    raw_text = str(inbound.get("text") or "")
    # The size cap lands before normalization and scanning: a hostile
    # message stays cheap.
    if len(raw_text.encode("utf-8")) > MAX_TEXT:
        raise BtError("message too long")
    text = render.normalize(raw_text)

    suggested = [
        v
        for v in (cases.num(a) for a in cases.as_list(inbound.get("amounts")))
        if v is not None
    ]
    if not suggested:
        suggested = money.amounts(text)

    # ``once`` has no conversion factor, so an inbound offer period
    # that differs from the floor's where either side is ``once`` can
    # never be verified: the band is unknown and the turn escalates,
    # never a raw-unit guess (the gate's offer rule).
    unconvertible = (
        in_period != floor_period
        and "once" in (in_period, floor_period)
    )
    escalate = []
    if offer is None:
        escalate.append("no_offer_parsed")
    elif unconvertible:
        escalate.append("offer_period_differs")
    if any(p.search(text) for p in INJECTION):
        escalate.append("suspected_injection")
    if any(p.search(text) for p in AI_QUESTION):
        escalate.append("ai_identity_question")
    if LEGAL.search(text):
        escalate.append("legal_terms")
    if offer is None or unconvertible:
        band = "unknown"
    else:
        converted = minor(
            render.convert(minor(offer), in_period, floor_period)
        )
        band = _band(
            direction,
            minor(target) if target is not None else None,
            minor(floor),
            converted,
        )
    return {"band": band, "escalate": escalate, "suggested_amounts": suggested}
