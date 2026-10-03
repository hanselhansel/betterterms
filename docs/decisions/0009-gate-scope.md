# 0009. Gate scope: two tiers, hard blocks and review

Status: amended by 0010 (was: accepted, owner decision, step 2 scope). Date: 2026-10-05.

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

## Amendment (2026-10-03): the review tier is an allowlist

The blacklist in section C kept missing variants (the same defect
class twice), so the review tier is rebuilt the other way around. It
still routes to the user and never blocks, but it no longer tries to
enumerate suspicious forms; it fails closed on anything unusual.

- The scan works on the rendered message with each non-fact
  placeholder output replaced by a sentinel, one reserved private-use
  codepoint. The free text passes only when every character is in the
  allowed set: ASCII letters and digits, ASCII space and newline, the
  punctuation `. , ; : ! ? ' " ( ) - / &`, and the sentinel. Any
  other character (non-ASCII letters, homoglyphs, control, format,
  combining, private-use and non-ASCII space characters, Hangul
  filler, braille blank, currency signs, symbols) is `needs_approval`
  "unusual characters". So is a template or fact that already carries
  the sentinel itself. Non-English messages therefore always go to
  the user.
- Free text tokenizes on non-alphanumeric characters in one linear
  pass. A token mixing letters and digits routes to the user. Under
  0010 a digit token passes only when it is isolated (no number-shaped
  token within two tokens) and is 1-99 written without a leading zero
  (and not equal to the floor's integer value when the floor is below
  100, in digits or as one number word), or it belongs to a
  whole-word month-name date. Decimals and separator-joined digit
  forms route to the user like any other number shape.
- Number words, scale words, currency words and commitment words
  stay as whole-word lists matched on the token stream. They live in
  one shared module (`scripts/btlib/wordlists.py`) that the
  guardrails SKILL.md quotes verbatim, pinned by a unit test. Under
  0010 every spelled number word and every scale abbreviation
  (including a bare k, m, mil or thou) routes to the user, singly or
  in combination.
- A sentinel touching a letter or digit still routes to the user.
- A rendered non-offer value equal to the floor exactly still
  blocks; equal only to an x12 or /12 conversion is now a review hit
  "amount matches a converted limit" instead of a block, so an
  explicit user yes can send it.
- Related fixes in the same pass: `accept` converts the inbound
  offer to the floor's declared period before comparing; the floor's
  period is declared as `floor_period` on the plan (the bare
  `period` keys still work); `cases.num` caps magnitudes at 1e12 so
  a huge offer blocks as "offer must be a number" instead of
  raising; `ledger add` validates `direction` through
  `cases.direction_of`; `score` and `money` inputs cap at 64 KB.

Amended by 0010: hard blocks no longer parse fact text at all; floor
rules read a fact's structured `amount` and `period` only, and
`money.py` serves `score` alone. The token rules above describe the
superseded forms; 0010's review list is the current contract.
