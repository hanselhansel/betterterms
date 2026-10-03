# 0010. Structural amounts only: hard blocks never parse free text

Status: accepted (owner decision, step 2 scope cut). Date: 2026-10-05.

## Context

0009 split the gate into hard blocks and a review tier, but facts
still ran the money parser on free text: render scanned each fact
body with `money.amounts` and fed the parsed values into the floor
rules. That kept a full text parser on the hard-block path, where a
parse miss is a floor leak and every miss argues for more patterns.
The owner cut the scope: hard blocks decide on structured values
only, and anything number-shaped in text goes to the user.

## Decision

A. Facts in `plan.yaml` carry `{id, text, source, amount, period}`.
   `amount` is a number or null; `period` is `once`, `month` or
   `year`, default `once`, and anything else is a broken plan
   (exit 2). Every hard-block floor rule that involves a fact
   (a rendered fact equal to the floor; a fact amount worse than
   the floor in an agreeing context, which is any action but
   `send`) reads only the structured amount, converted from the
   fact's own period to the floor's. The gate never runs money
   parsing on fact text. A fact id in `claims` that no `{fact:id}`
   placeholder renders is checked only for membership in
   `plan.facts`; its `amount` joins no floor comparison because its
   text is not sent.

B. The review tier (`needs_approval`, never a silent pass) is
   stricter and simple, over the rendered text with non-fact
   placeholder outputs masked plus every rendered fact's text. Hits:
   any spelled number word (zero through ninety, hundred, thousand,
   million, billion, and combinations); any decimal or
   separator-joined digits; any digit token that is not isolated
   (within two tokens of another digit token, a number word, or a
   currency or scale word or abbreviation such as k, m, mil, mm,
   bn, thou, grand); any currency word, code or symbol; and any
   fact whose text contains digits or number words while its
   `amount` is null. Only isolated 1-2 digit integers (1-99, no
   leading zero) and whole-word month-name dates pass. The
   character allowlist, the sentinel rules and the commitment-word
   rules from the 0009 amendment are unchanged. Decimals that read
   as small integers under the 0009 amendment ("90.5") now route
   to the user.

C. `money.py` stays only for `score`'s `suggested_amounts` and the
   inbound-amount fallback. Nothing on the gate path imports it:
   the numeric `never_disclose` match reads the token stream
   (digit tokens and separator-joined groups) instead of a money
   scan.

D. Fixes landed with the cut: fact expansion stops resolving once
   the rendered size passes 64 KB (size still comes from piece
   lengths, never a joined string); an `action` that is a list or
   mapping blocks (exit 1) instead of crashing on the membership
   check; decimals go to review per B.

## Consequences

The hard-block path carries no free-text parser at all: floor rules
read the offer, the plan's price values, the inbound amounts and
each fact's `amount` field. Anything number-shaped in text, money
or not, routes to the user with a plain-word reason, so the losing
game of enumerating spellings stays over. The skills record
`amount` and `period` on every fact that states money; a fact that
states money without them still sends, but only after the user
sees it.
