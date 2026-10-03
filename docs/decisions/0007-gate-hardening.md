# 0007. Gate hardening: close the fail-open holes

Status: amended by 0009 (was: accepted, owner decision list, step 2 review). Date: 2026-10-04.

## Context
Review of the step 2 gate found places it could pass a draft the floor
should stop: the floor only compared the `offer` field, not the amounts
in the text; block reasons named the floor's distance and direction; a
missing or corrupt `.floor` errored in some paths and defaulted in
others; a plan could disagree with the floor unchecked; the floor value
could be piped through `printf` into shell history; and `accept` could
take an inbound offer that was itself outside the band.

## Decision
A. The user enters the floor, not the model. `bt.py case set-floor`
   reads with `getpass` (prompt "Walk-away number (hidden): ") when
   stdin is a TTY, else from stdin. Intake tells the user to run it in
   their own terminal; only when they cannot does the agent pass it on
   stdin with a quoted heredoc, and then tells the user the agent saw
   the value once. The "you will not see it again" claim is removed.
B. Number parsing is strict: `parse_number` accepts only `\d+` or
   `\d+.\d+` with a decimal tail that is not three digits; it rejects
   nan, inf, negatives, empty input, multiple numbers, leading commas,
   and ambiguous separators with one fixed message. A missing,
   unreadable, or invalid `.floor` blocks the gate and exits 2 in the
   scorer.
C. The floor rule covers every marked amount in the text (pay: above
   the floor; receive: below it), with one exception: amounts quoted
   from the counterparty's own inbound text or offer pass only when the
   draft's numeric offer is inside the band. `accept`, `sign`, and
   `pay` require a numeric in-band offer; `accept` may not take an
   inbound offer that is itself outside the band.
D. Money parsing adds `one thousand, two hundred`, `1 200`, `1.2
   grand`, `1200ish`, `~1200`, `1,200-ish`, `12 hundred`, `$1.2k`, and
   per-period forms (`1200/mo`, `1200 a month`) as marked amounts, plus
   a digits-only scan for the floor's digit string. Numeric
   `never_disclose` items are normalized through money parsing.
E. Every floor-related block reports one generic reason, "outside your
   limits; escalate to the user". The gate can still be probed by
   repeated calls: it has no way to see or rate-limit its own
   invocations, and the generic reason keeps each call from leaking
   direction or distance. The mitigation sits in the skills, which cap
   gate calls per turn: on a floor-related block the skill redrafts at
   most once, then escalates to the user instead of redrafting toward
   a guessed limit.
F. `direction` must be `pay` or `receive` (else exit 2). The scorer
   checks the floor before the target. A plan target, option, or ladder
   value outside the band exits 2 with "plan conflicts with your
   limits". A null or non-numeric inbound offer gives band `unknown`
   and escalate `no_offer_parsed`.
G. Money regexes stay linear-time; processed text is capped at 64 KB
   ("message too long"); `find()` merges span sets per pass instead of
   scanning them per match.
H. The ledger rejects non-finite or negative amounts and duplicate
   `case_id` entries.
I. Coach mode and autonomy 1 make every send `needs_approval`; the user
   restates or confirms limits and the agent never asks for the floor
   in chat.
J. `--approved` is passed only after an explicit user yes in the
   current conversation, quoted in `thread.md`.

## Consequences
The gate is fail-closed on every path the review flagged: unreadable
inputs block, every amount is checked, and no block reason can oracle
the floor. Tests pin the strict parse table, the TTY prompt, the
crossing rule and its quote exception, the generic reasons, the 64 KB
cap, the new bands, and the ledger guards.
