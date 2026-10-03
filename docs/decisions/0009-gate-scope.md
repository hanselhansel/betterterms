# 0009. Gate scope: two tiers, hard blocks and review

Status: accepted (owner decision, step 2 scope). Date: 2026-10-05.

## Context

ADR 0008 moved all money into rendered placeholders and then tried to
keep the literal text airtight: any digit run, currency mark, scale
word, number-word run, invisible character or small integer matching
the floor blocked the draft. That kept the old losing game from 0007
alive in a smaller arena. The set of ways to write a number is still
unbounded, every miss argued for a new regex, and each new regex made
the gate slower and the reason strings harder to keep leak-free. The
owner narrowed the goal: the gate must guarantee a small list of
structural properties in code, and route everything suspicious to the
user instead of trying to prove the text clean.

## Decision

The gate has two tiers.

A. Hard blocks are code guarantees and fail closed: a missing,
   unreadable or invalid `.floor`; an invalid brief (direction, mode,
   autonomy); a missing or unknown `action`; unknown draft keys or a
   legacy `text` key; an `offer` that is not a plain number; a
   structured offer worse than the floor after period normalization;
   `accept`, `sign` and `pay` without a numeric in-band offer; an
   `accept` whose offer differs from an in-band inbound offer or whose
   inbound offer is worse than the floor or non-numeric; unknown claim
   ids; unknown or malformed placeholders; any rendered placeholder
   value equal to the floor or its x12 or /12 conversions except the
   offer itself; plan price values that conflict with the floor; and a
   rendered message over 64 KB, checked after fact expansion and
   before any text scanning.
B. Period comparison is declared, not guessed: the plan or brief
   declares the floor's period (default `once`); month x12 = year;
   `once` mixed with a recurring period compares raw values. Options
   with `kind: bonus` or `kind: fee` are not offers, so they skip the
   worse-than-floor check at plan and render time; they still may not
   render a value equal to the floor.
C. The review tier routes to the user as `needs_approval` and never
   passes silently. The gate scans the rendered message with every
   non-fact placeholder output masked out (fact text stays visible: it
   is user data, not a guaranteed price). Review hits: money or a
   number of 3 or more digits; a digit next to a rendered amount
   (`{offer}0`); currency symbols or codes, case-insensitive; money or
   scale words; a run of number words; agreement or commitment wording
   (deal, agree, accept, works for me, happy to pay, go ahead, charge,
   process it, sign me up, cancel my, confirm); invisible or format
   characters (Unicode category Cf, Mn joiners, soft hyphen, bidi
   marks) and non-ASCII digits; and any `never_disclose` term after
   NFKC normalization and Cf stripping, with numeric items matched as
   whole numbers only. Each reason is plain words with no numbers.
D. Free-text detection is no longer airtight, on purpose. The code
   that tried to prove literal text money-free is deleted; what
   remains is a detector that routes suspicious messages to the user.
   Small integers 1-99 stay fine unless the floor is below 100 and the
   integer equals its integer part (floor 89.99 does not make "7 days"
   a review item). A 4-digit year 1900-2100 next to a month name is a
   date, not an amount ("October 15, 2026" passes).
E. `money.py` stays for `suggested_amounts`, fact values and
   never-disclose matching. Its parsed values saturate instead of
   raising or yielding infinity, and the whole scan is linear on
   hostile input. `score.py` normalizes inbound text (NFKC plus Cf
   stripping) before its injection, AI-identity and legal matching.
   Placeholder indexes accept ASCII digits only, so a superscript or
   non-ASCII digit blocks instead of crashing or reading a different
   index.

## Consequences

The gate's contract is now a list the code can actually promise:
everything structural fails closed, everything textual goes to a human
with a plain-word reason. The floor still cannot leak through reasons
(generic, number-free) or through rendered output on a block (null).
Tests pin every pass-3 probe as either a hard block when it is
structural or needs_approval when it is textual, and never a silent
pass.
