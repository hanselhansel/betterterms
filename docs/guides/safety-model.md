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

Two other entry paths land in the same file: the mod's terms editor
writes it through `case set-floor` on stdin, and a `bt floor
<case_id> <amount>` chat message is caught by a `UserPromptSubmit`
hook, written through stdin, and blocked so the model never receives
it. In a Projects thread that message stays visible to project
members, so the terminal stays the better path there.

State the boundary plainly: the agent runs as your user, so nothing
technical stops it from reading `.floor` if it
tries (decision [0019](../decisions/0019-guard-deferred.md) is why the
limit is stated, not enforced). The skills instruct it never to, and
the gate blocks any draft that states the walk-away.

## The gate's two tiers

`bt.py gate` checks each draft and returns `pass`, `block`, or
`needs_approval`. The contract is two tiers; [decision
0009](../decisions/0009-gate-scope.md) has the full list.

**Tier 1: hard blocks.** Structural rules that fail closed. A missing or
invalid floor file blocks. An offer worse than your number blocks. `accept`,
`sign`, and `pay` block without a numeric in-band offer, and `accept` blocks
unless it matches an in-band inbound offer. Unknown placeholders, unknown
claim ids, a rendered placeholder value equal to your number, and a
message over 64 KB all block. A block returns reasons and no rendered
text, so nothing can leave "as drafted".

**Tier 2: review.** The gate renders the draft, masks the placeholder outputs,
and scans the remaining free text. Money-shaped text, any digit in the
free text, commitment wording ("deal", "works for me", "sign me up"), a
`never_disclose` term, non-English characters, and anything else
unusual route the draft to you as `needs_approval`. Tier 2 does not try
to prove the text is clean. It fails closed on anything it cannot classify,
so a human reads the odd cases.

Drafts carry no typed prices at all. Money enters a message only through
placeholders the gate renders itself: `{offer}`, `{target}`,
`{option:<label>}`, `{ladder:<n>}`, `{fact:<id>}`, `{quote:<n>}`. See
[decision 0008](../decisions/0008-structured-amounts.md).

Every floor-related block reports one generic reason ("outside your limits;
escalate to the user"), so no single gate answer states the number. A
determined agent could still probe the gate with repeated guesses until a
block flips to a pass, which is why the skills cap gate calls per turn (a
probe counter is tracked in TODOS). See
[decision 0007](../decisions/0007-gate-hardening.md) for the hardening list.

## Held drafts and hash-bound approvals

A `needs_approval` verdict does not hold a send open; it parks the
draft. The gate writes `held/<hash>.yaml` in the case folder with the
rendered text and reasons, and returns the `hash`. The draft waits for
you there, minutes or days, and survives restarts.

Approval is bound to the SHA-256 of the send tuple (action, offer,
period, currency, and the exact rendered text), recorded
as `held/<hash>.approved`, and written only by a user action:

- a keypress or click on Approve in the `betterterms-mod` Approvals
  tab,
- your own `bt approve <case_id> <hash8>` message caught by the
  prompt hook (a widget button types it for you), or
- `bt.py held approve`, run by the agent only in a host with no
  prompt hook and only after you typed `bt approve`.

The gate accepts `--approved` only when an approval file matches the
hash of the newly rendered text, and it consumes the file after one
use: the marker is claimed by an atomic rename, so two racing sends
can never share one approval. Edit the text and the old approval no
longer matches: the draft is held again. Typing "yes" in chat approves
nothing.

Held records from before tuple-bound names (the filename hashed the
rendered text alone) still list, flagged `legacy: true`. They cannot
be approved or spent; re-run the gate to hold the draft under the
current hash.

The mod does not inspect outgoing tool calls or prompts (decision
[0020](../decisions/0020-mod-send-check-deferred.md)). A pane press
runs `bt.py held approve`, which writes the marker for that exact
hash, and submits a prompt telling the agent to run `bt.py gate
<case> --approved` once and send the returned rendered text verbatim.
In every mode the marker is the approval the gate spends, and the
only one.

`bt reject <case_id> <hash8>` drops the held draft. `bt terms
<case_id> target=<a> alternative=<b>` writes target and best
alternative to `plan.yaml` (`bt terms` takes either key alone, in any
order). Both come through the same prompt hook. Of the typed commands
only `bt floor` is kept from the model where the hook runs; `bt
approve`, `bt reject` and `bt terms` are handled first, then passed
through with a note.

## Display modes, stated plainly

| Mode | Where | What approval means |
|---|---|---|
| Mod | Claude Code terminal or Desktop with `betterterms-mod` | A keypress or click runs `bt.py held approve` for the displayed hash and submits the prompt that sends the agent through `bt.py gate --approved` once. The mod is a cockpit only: it never inspects outgoing tool calls (decision 0020). |
| Widget | Projects cloud threads with a widget-posting tool | A `held/<hash>.approved` file written by the prompt hook after your typed `bt approve` (the widget button only fills the message box; you press Enter). |
| Chat | Codex, plain cloud sessions, `claude -p` | The same typed commands and the same approval file; with no prompt hook the agent runs `bt.py held approve` after you type `bt approve`. |

All three modes share one enforcement: the gate's hash-bound one-use
`--approved` marker. They also share one limit: the agent runs as
your user, so nothing technical stops a forged marker or an ungated
send if it sets out to; the skills' instruction never to is the
boundary there (decision 0019).

Every mode shares the guarantee that counts most: text inside an
inbound message can never become a user message, so it can never
approve a draft. In a Projects wake envelope, only the `from="human"`
triggering body counts as you.

## What the gate does not do

- It is a safety net, not a sandbox. It checks drafts that go through
  `bt.py gate`. An agent acting outside that path is outside its reach. The
  skills route every send through the gate, and the default autonomy asks
  before every send, which keeps a human on each turn.
- With or without the mod, the agent runs as your user. Nothing
  technical stops it from reading the walk-away file, writing an
  approval marker, or sending ungated text if it tries; the skills
  instruct it never to, and the gate blocks any draft that states the
  walk-away. Decision
  [0019](../decisions/0019-guard-deferred.md) covers the limit.
- It checks structure, not truth. A sourced fact can still be wrong; source
  records carry URLs and read dates so you can check them.
- It does not rate-limit itself. The skills cap gate calls per turn and
  redraft at most once before escalating, which is the standing mitigation
  for probing: enough guesses against the floor comparison could triangulate
  the number, so a dedicated probe counter is on the TODO list.
- It does not replace your yes. Accept, cancel, pay, sign, and dispute always
  wait for an explicit approval, at every autonomy level.

## Known limits, stated plainly

- A shared Projects thread is single-trust: any member can approve a
  draft or set the walk-away, so keep sensitive cases out of shared
  threads.
- `bt.py score` reads the same `.floor` the gate does, so it can be
  probed for the number the same way.
- `scripts/vendor-into-repo` enables the plugin unpinned; a vendored
  repo tracks whatever the marketplace serves.
- An approval binds the send tuple, not the recipient: it does not
  check who the message goes to.
- Amounts typed with a decimal comma parse as thousands separators
  (`62,50` reads as 6250); use a dot.

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
