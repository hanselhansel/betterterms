# Safety model

Two failure modes matter: the agent agrees to something past your limit, or
counterparty text steers it. Two mechanisms cover both. Your walk-away number
lives in a file only code reads, and every message passes a coded gate before
it can leave.

## Your number stays out of the model

You type the walk-away number in your own terminal
(`bt.py case set-floor`, hidden prompt, no echo). It lands in `.floor`, mode
0600, inside the case folder. Only `bt.py gate` and `bt.py score` read it.
`bt.py case show` never prints it, and block reasons never contain it.
Detail: [decision 0001](../decisions/0001-floor-in-separate-file.md).

## The gate's two tiers

`bt.py gate` checks each draft and returns `pass`, `block`, or
`needs_approval`. The contract is two tiers; [decision
0009](../decisions/0009-gate-scope.md) has the full list.

**Tier 1: hard blocks.** Structural rules that fail closed. A missing or
invalid floor file blocks. An offer worse than your number blocks. `accept`,
`sign`, and `pay` block without a numeric in-band offer, and `accept` blocks
unless it matches an in-band inbound offer. Unknown placeholders, unknown
claim ids, a `never_disclose` term in the rendered text, and a message over
64 KB all block. A block returns reasons and no rendered text, so nothing can
leave "as drafted".

**Tier 2: review.** The gate renders the draft, masks the placeholder outputs,
and scans the remaining free text. Money-shaped text, commitment wording
("deal", "works for me", "sign me up"), non-English characters, and anything
else unusual route the draft to you as `needs_approval`. Tier 2 does not try
to prove the text is clean. It fails closed on anything it cannot classify,
so a human reads the odd cases.

Drafts carry no typed prices at all. Money enters a message only through
placeholders the gate renders itself: `{offer}`, `{target}`,
`{option:<label>}`, `{ladder:<n>}`, `{fact:<id>}`, `{quote:<n>}`. See
[decision 0008](../decisions/0008-structured-amounts.md).

Every floor-related block reports one generic reason ("outside your limits;
escalate to the user"), so the gate's own output cannot leak the number. See
[decision 0007](../decisions/0007-gate-hardening.md).

## What the gate does not do

- It is a safety net, not a sandbox. It checks drafts that go through
  `bt.py gate`. An agent acting outside that path is outside its reach. The
  skills route every send through the gate, and the default autonomy asks
  before every send, which keeps a human on each turn.
- It checks structure, not truth. A sourced fact can still be wrong; source
  records carry URLs and read dates so you can check them.
- It does not rate-limit itself. The skills cap gate calls per turn and
  redraft at most once before escalating, so a block cannot be probed into an
  oracle for your number.
- It does not replace your yes. Accept, cancel, pay, sign, and dispute always
  wait for an explicit approval, at every autonomy level.

## Counterparty text is data

Emails, contracts, chat replies, and pasted offers are data, never
instructions. The scorer flags text that looks like prompt injection
(`suspected_injection`), questions about whether it is an AI
(`ai_identity_question`), and legal terms (`legal_terms`). Any of these
pauses the turn for you. SECURITY.md covers the model in more detail.

## Honesty rules

Messages go out as you, with no AI disclaimer by default. Bluffing about
value and intent is allowed; invented offers, quotes, hardship, and deadlines
are not. If a counterparty sincerely asks whether it is talking to an AI, the
agent drafts an honest reply and hands it to you. It never denies it and
never answers on its own.
