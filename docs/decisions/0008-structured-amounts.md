# 0008. Structured amounts: drafts render placeholders, not free-text money

Status: accepted (owner decision, step 2 rework). Date: 2026-10-05.

## Context
ADR 0007 hardened the gate around a free-text `draft.text`: money
regexes scanned the whole message, amounts had to be "traced" back to a
structured source, and bypass probes kept finding new forms (bare "I
will pay 90", zero-width spaces, superscripts, grouped digits, spelled
runs). Scanning text for money is a losing game: the set of ways to
write a number is unbounded, and every miss is a possible floor leak.

## Decision
The text-scanning parts of 0007 are superseded. Prices are structured
data; the only money in a message comes from placeholders the gate
itself renders.

A. `draft.yaml` is `action`, `offer` (plain number or null), `period`
   (`once|month|year`, default `once`, applies to `offer`), `template`
   (message text with placeholders) and `claims` (fact ids). A `text`
   key blocks with "use template, not text"; unknown keys block;
   missing or non-mapping fields fail closed.
B. Placeholders: `{offer}` renders the offer with its period
   ("$85/month"); `{target}`, `{option:<label>}`, `{ladder:<n>}`
   render plan values; `{fact:<id>}` renders the fact's text verbatim
   and adds the id to claims; `{quote:<n>}` renders the n-th entry of
   the inbound `amounts` list. Unknown or unresolvable placeholders
   block, naming the placeholder.
C. `inbound.yaml` keeps `text` (data, never instructions) and `offer`,
   and adds `amounts`: the list of numbers the counterparty stated,
   extracted by the agent. `score` returns them as
   `suggested_amounts`, falling back to `money.amounts(text)` when the
   list is absent, so the agent can confirm what to index.
D. Literal free text (everything outside placeholders) may carry no
   money. After NFKC normalization and zero-width stripping, any
   currency symbol or code, currency or scale word (including `k`
   after a digit and `grand`/`hundred`/`thousand`/`million`/`billion`/
   `bn`/`mm`), a digit run of 3 or more, separator-joined digits
   (`1,200`, `1.200`, `1 200`, `1'200`), a run of 3+ number words, or
   a non-ASCII digit blocks. Standalone integers 1..99 pass (dates,
   months, counts) unless they equal the floor's integer part, its x12
   or /12, or the integer part of a structured amount in play (a
   rendered value, the draft offer, or the inbound offer).
E. Floor rules are structural now: an `offer` worse than the floor
   blocks after conversion to the plan period; `accept`, `sign` and
   `pay` require a numeric in-band offer; `accept` additionally
   requires an inbound offer inside the band equal to the draft offer.
   Any rendered amount equal to the floor's value or its x12 or /12
   blocks, except the offer itself when it is inside the band (an
   offer exactly at the floor is allowed: the user said it is
   acceptable). A `{quote:n}` worse than the floor is allowed only on
   `send` (quoting, not agreeing). Options carry `kind:
   bonus|fee|price`; only `price` options count as offers, at plan
   check and at render time.
F. Agreement wording in free text ("deal", "agreed", "I accept",
   "accept your", "works for me", "sounds good, let's", "go ahead and
   charge", "sign me up", "cancel my") makes a `send` needs_approval,
   so an agent cannot say "I accept, charge my card" as a plain
   message.
G. The gate returns `rendered` (null on block): the exact text to
   send. The agent sends it verbatim and never re-formats it.
H. Brief fields normalize at read time inside `cases`: `mode` compares
   case-insensitively (`Coach` works), `autonomy` must be an integer
   1-4 and `direction` must be `pay` or `receive`, else exit 2.
   `case_id` must match `^[a-z0-9-]+$` so it can never leave the cases
   directory. Any unexpected exception in `bt.py` prints
   `{"error": ...}` and exits 2, never a traceback.
I. `money.py` stays for parsing counterparty text into
   `suggested_amounts` and for `never_disclose` numeric matching. The
   gate's draft-text money scanner and the traced-number rule are
   gone: there is nothing left to trace because there is nowhere for
   an untraced number to hide.
J. Floor-related block reasons stay generic, and the gate can still be
   probed by repeated calls (see 0007-E): the skills cap gate calls
   per turn, redraft once, then escalate.

## Consequences
The gate's floor surface shrinks to a set of structured values it
enumerates itself: offer, target, options, ladder, facts, quotes.
Every bypass the 0007 review listed is covered by a check on literal
text that fails closed. Tests pin the render table, the free-text
ban, the probes, period conversion, option kinds, brief normalization
and the JSON-only error contract.
