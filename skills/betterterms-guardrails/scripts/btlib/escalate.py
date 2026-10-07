"""The inbound stop rule the gate enforces (decision 0021).

A draft that answers an inbound message whose real score band is
``unknown``, ``near_floor`` or ``below_floor``, or whose escalate
list is non-empty (``no_offer_parsed``, ``offer_period_differs``,
``suspected_injection``, ``ai_identity_question``, ``legal_terms``),
is only ever a proposal: the gate holds it for the owner's approval
at every autonomy level, and nothing reaches the counterparty until
the owner spends a hash-bound approval on it.

The gate asks ``score.classify`` itself, so the check reads the
case's real ``.floor`` and the inbound mapping that was supplied --
never a band or flag the caller asserts in the file. A supplied
inbound the scorer cannot classify (a message over the text bound,
or any refusal ``classify`` raises) holds too: the gate never
autonomously passes a turn it cannot score. Blocks still dominate:
when the draft or the case already fail closed, the extra approval
finding never reaches the reason list. An opening turn carries no
inbound and is untouched.
"""

from . import BtError, score

STOP_BANDS = frozenset({"unknown", "near_floor", "below_floor"})

# The one reason the stop rule reports: plain words, no number, no
# band name and no flag name, so a held proposal never leaks where
# the floor sits or which trigger fired.
REASON = "the counterparty's message needs your review"


def holds(case_dir, inbound):
    """True when the real score of ``inbound`` stops autonomous
    action on this turn: a stop band or a non-empty escalate list.
    ``None`` means an opening turn, which never stops; a supplied
    inbound the scorer refuses holds as well, since an unscorable
    turn is never grounds for a pass."""
    if inbound is None:
        return False
    try:
        scored = score.classify(case_dir, inbound)
    except BtError:
        return True
    return scored["band"] in STOP_BANDS or bool(scored["escalate"])
