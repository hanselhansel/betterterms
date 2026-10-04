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

## Amendment (2026-10-04): a send offer at the floor routes to the user

An offer exactly at the floor is inside the band, so it rendered
like any other in-band price. On `send` the offer is the
counter-offer on the table, though: sending it hands the
counterparty the user's walk-away number. A `send` draft whose
offer equals the floor, compared in the floor's declared period
within the comparison tolerance, is now `needs_approval` with the
number-free reason "offer is at your limit"; an explicit
`--approved` still sends it. `accept`, `sign` and `pay` are
unchanged: they may sit exactly on the floor because they take a
price already on the table.

## Amendment (2026-10-04): digits always route; number words match substrings

The B exceptions leaked: isolated small integers ("over 12 may
not") and whole-word month-name dates ("June - 1950") each gave
suspicious text a pass, through three different code paths. They
are removed. The rule is now absolute: any ASCII digit in the
free text or in a rendered fact's text routes to `needs_approval`
with "numbers in the message". The tier never parses digits into
numbers: no `int` or `float` call touches the text, so a digit run
of any length cannot crash or stall the scan. The small-integer,
sub-100 floor-integer and month-name-date machinery
(`_small_number`, `_isolated`, `_moneyish`, `_is_year`,
`_date_parts`, `_whole_numbers`, `MONTH_WORDS`,
`NUMBER_WORD_VALUES`) is deleted with them.

- Number words are matched as substrings of each lowercased
  letter run, so glued forms ("twelvehundred", "fiftyish") flag
  too. Whole-run exceptions hold for a fixed list of common
  English words that contain a number word ("often", "tone",
  "money"): the run must equal the listed word, so "oftener"
  still flags. The exception list was computed with a standard
  approach: a standard common-English word list (the top 10,000
  of google-10000-english), keep every word containing a number
  word that the number-parse rule does not flag (a word parses
  when it equals a number word, starts or ends with one and the
  remainder is another number word, a scale word or empty, or is
  a concatenation of number and scale words), then drop
  number-derived leftovers (ordinals like "fourth", compounds
  like "threesome") and non-English artifacts. "ones" stays: it
  is anaphoric English, not a count.
- A `send` offer whose digits equal the floor's digits in a
  period that is not the floor's routes with "amount matches your
  limit's digits" ("$1,200/year" against a 1,200/month floor).
  The converted value clears the band but the digits still
  restate the walk-away number. `accept`, `sign` and `pay` are
  exempt because they may restate a price the counterparty
  named. Same-period equality still routes as "offer is at your
  limit"; a non-offer value equal to the floor still blocks.
- Numeric `never_disclose` items still match fused digit runs in
  the text as whole digit strings ("1,200" and "12 00" hit item
  "1200", "420" does not hit "42") and now also compare against
  rendered placeholder values, so the term still matches behind
  the mask.
- The fact-amount review carve-out is gone with the exceptions:
  fact text scans like any other free text, so a fact whose text
  carries digits or number words routes whether its `amount` is
  set or null.
- Currency words add cents, cent, pesos, peso, rupees, rupee,
  won, francs, krona, krone, rand, ringgit, baht, dong, lira,
  real, reais, shekel, zloty, dirham, riyal and naira (yuan and
  quid were already listed). Commitment wording adds "take it",
  "i'll take", "we'll take", "cancel", "let's do", "sold", "you
  have a deal" and "count me in". Tokens keep interior
  apostrophes, so "i'll" is one word and "won't" is not "won".

## Amendment (2026-10-04): scale words match substrings; unconvertible periods fail closed

- The singular scale words (hundred, thousand, million, billion,
  trillion) plus "grand" match as substrings of each lowercased
  letter run, like number words: "halfmillion", "thousandfold",
  "hundredish" and "grandtotal" route to `needs_approval`. The
  abbreviation forms (k, m, mil, mm, bn, thou) stay whole-token
  only; inside a run they are ordinary letters ("milk"). The
  whole-run exception list covers the common English words the
  substring rule would catch ("attentive", "softened", "tenure",
  "oftentimes", "honestly", "nonetheless", "phoned", "frightened",
  "bitten", "intentionally", "listened", "phoning", "toned" and
  the earlier entries).
- `once` has no conversion factor, so an offer or inbound offer
  period that differs from the floor's declared period where
  either side is `once` can never be verified against the floor.
  Raw comparison was the old behavior and compared unlike units.
  A `send` draft now routes to `needs_approval` with "period
  differs from your limit" ("{offer} per month" against a `once`
  floor), and `accept`, `sign` and `pay` block unless the periods
  match or a month/year conversion applies. The same rule covers
  the inbound offer's period on `accept` (a 1100/month draft
  against a 1100/year inbound with a `once` floor blocks).

## Amendment (2026-10-04): word lists are best effort

Owner decision on 2026-10-04. The guarantees are the hard blocks on structured numbers, the
character allowlist, and the rule that any digit routes to the user. The number, scale, currency
and commitment word lists are a best-effort extra signal, not a guarantee: no finite list covers
every spelling, plural, inflection or foreign word. Known gaps are tracked in TODOS.md. The
default autonomy (approve each send) means a missed word reaches the user before it is sent.

## Amendment (2026-10-04): fail-closed values, canonical floors, declared currency

- The unconvertible-period rule covers every price value, not only
  the offer. A plan target, ladder step or price option whose
  period cannot convert to the floor's (`once` on either side)
  blocks when rendered or offered, and so do quote and fact amounts
  on every action but `send`. The send carve-out is retained: a
  `send` may still render a counterparty quote or fact amount that
  is worse than the floor or in a period that cannot be converted,
  because restating a price the counterparty named is not the
  agent's offer. Only the agent's own offer routes "period differs
  from your limit" on `send`; the agreeing actions block. Bonus
  and fee options keep their equality-only check.
- The `.floor` file hardens. `set-floor` probes the target with
  `O_NOFOLLOW` and refuses a symlink or non-regular file, writes a
  0600 temp file in the case directory, fsyncs it and renames it
  into place with `os.replace`. `read_floor` lstat-checks and
  treats anything but a regular file as missing, and a `.floor`
  that is not valid UTF-8 is an unreadable floor (block), never a
  traceback. Case directories and `BETTERTERMS_HOME/cases` are
  created 0700.
- The floor is stored in canonical two-decimal form. `set-floor`
  accepts only a plain number that stores exactly in the currency
  minor unit and is at least 0.01; anything else errors before an
  existing floor is touched.
- Every limit comparison reads the value as rendered, rounded to
  the minor unit, before and after period conversion. An amount
  that renders onto the floor is the floor (100.005 against a
  100.00 floor routes a send "offer is at your limit"; 100.006
  renders "100.01" and blocks), so a rendered amount can never land
  past the floor inside the raw comparison tolerance.
- Currency is declared, not guessed: `brief.yaml` or `plan.yaml`
  may carry an ISO code (default USD; conflicting declarations are
  exit 2). Rendered amounts use the matching symbol ($, S$, euro
  sign, pound sign) or the code before the number. The ledger
  records the case currency on each entry and totals group by
  currency; amounts in different currencies are never summed.
- `score.py` reads the inbound offer in its own period and converts
  with the gate's rules. An unconvertible inbound period bands
  "unknown" with escalate "offer_period_differs" instead of
  comparing unlike units; a present non-string or unknown inbound
  period is exit 2; absent defaults to the floor's period.
