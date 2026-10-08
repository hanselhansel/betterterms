# 0016. Quote rule, never_disclose blocks, and step-2 gate fixes

Status: accepted (release lane R2, spec 4.1, 4.3, 4.4).
Date: 2026-10-06.

## Context

The release plan's step-2 review confirmed six findings against the
gate and ledger, and the quoting rule needed one home: `gate.py` had
reached the 400-line cap. Two findings were false positives already
handled (a numeric `never_disclose` item inside a fact's structured
`amount` was already compared as a value; a `period` key naming a
non-string was already exit 2), one was a test-only artifact. The
rest needed contract changes.

## Decision

A. Quoting is not offering (spec 4.4). `{quote:n}` renders the n-th
   entry of the inbound `amounts` list: a number renders as money
   like before, a string renders the counterparty's words verbatim.
   A quote never meets the worse-than-floor or the
   unconvertible-period check on any action (it used to keep only a
   `send` carve-out). It may still not equal the floor: a rendered
   value equal to the walk-away number leaks it regardless of who
   wrote it. A verbatim string quote is NOT masked for the review
   tier: inbound.yaml is written by the agent, not by the
   counterparty, so the words it carries are the agent's to vouch
   for and every review rule (digits, commitment wording, unusual
   characters, the allowlist) applies to them exactly as to the
   agent's own text. Masking them would let a smuggled string bypass
   review entirely.

B. A `never_disclose` item with letters is a hard block wherever it
   appears in the rendered text, verbatim quote text included. A
   listed term is never a coincidence, so routing it to review would
   only offer a rubber stamp. Numeric items stay review-tier: they
   compare against fused digit runs (which now include quote text,
   since string quotes stay in the masked scan) and rendered
   placeholder values.

C. A `period` key present but null on an option, a ladder step, a
   fact, the plan, the brief or the inbound file is a broken file:
   exit 2, never a silent default. Only an absent key defaults.
   (The draft's own `period: null` stays "not set" and defaults to
   `once`.)

D. A blocked draft never reports "offer is at your limit": on a
   block the reason would leak the floor's equality bit, so it joins
   `DROP_ON_BLOCK` with the converted-limit and same-digits hits.

E. The ledger holds an flock across the read-dedupe-append sequence
   in `add`, so a racing add of the same case loses instead of
   double-recording; `total` reads under a shared lock. `add`
   appends the newline a file is missing before writing its own
   line, and a line nested past the interpreter's JSON recursion
   limit counts as corrupt input (a warning), never a crash.

F. Shipped templates pass their own gate (spec 4.3).
   `scripts/_lib/checks_templates.py` renders every fenced block in
   `skills/*/references/templates/*.md` against the fixture case in
   `tests/fixtures/template_case` at autonomy 3 and 4 and fails
   verify with the template path when a block trips the gate.
   `<slot>` markers are agent fill-ins, so a stand-in word replaces
   each before gating. A commitment phrase directly negated in the
   two tokens before it ("no longer works for me") reads as a
   decline, not a commitment; `milestone` joins the common-English
   number-word exceptions. Commit wording, count words and literal
   digits in template bodies were reworded rather than exempted.

## Layout

`btlib/quotes.py` owns the quote-amount rule (`check_values`,
`converted_match`, `floor_digits`) so `gate.py`
stays under the file cap; the floor helpers it shares
(`worse`, `same`, `in_floor_period`) moved with it. `review.py`
keeps the text scan plus the lettered-item `disclosed` probe the
gate calls for the hard block.
