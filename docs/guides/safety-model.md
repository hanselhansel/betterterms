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
members, so the terminal stays the better path there; a
`PreToolUse` hook also denies reads of `.floor` files, `held/`
records, and the session transcript.

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
block flips to a pass, which is why the skills cap gate calls per turn and
the mod watches tool calls (decision
[0017](../decisions/0017-display-modes-and-widget-fallback.md) states the
limit; a probe counter is tracked in TODOS). See
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
use. Edit the text and the old approval no longer matches: the send is
denied and the draft is held again. Typing "yes" in chat approves
nothing.

`bt reject <case_id> <hash8>` drops the held draft. `bt terms
<case_id> target=<a> alternative=<b>` writes target and best
alternative to `plan.yaml` (`bt terms` takes either key alone, in any
order). Both come through the same prompt hook.

## Display modes, stated plainly

| Mode | Where | What approval means |
|---|---|---|
| Mod | Claude Code terminal or Desktop with `betterterms-mod` | A keypress or click recorded in mod state the agent cannot write. The strongest path: no file the agent creates, and no text in a counterparty's email, can approve a draft. |
| Widget | Projects cloud threads with a widget-posting tool | A `held/<hash>.approved` file written by the prompt hook after your typed `bt approve` (the widget button only fills the message box; you press Enter). Weaker than the mod: the agent can write files, so the `PreToolUse` guard denying writes under `held/` is the only guard against a forged approval, and it is best effort. |
| Chat | Codex, plain cloud sessions, `claude -p` | The same typed commands and the same approval file; with no prompt hook the agent runs `bt.py held approve` after you type `bt approve`. Same strength as the widget mode. |

Every mode shares the guarantee that counts most: text inside an
inbound message can never become a user message, so it can never
approve a draft. In a Projects wake envelope, only the `from="human"`
triggering body counts as you.

## What the gate does not do

- It is a safety net, not a sandbox. It checks drafts that go through
  `bt.py gate`. An agent acting outside that path is outside its reach. The
  skills route every send through the gate, and the default autonomy asks
  before every send, which keeps a human on each turn.
- Outside the mod, the agent runs as your user. The `PreToolUse` guard
  scopes private state to the betterterms home and normalizes quoting and
  path tricks, but a same-user agent that sets out to bypass it can: only
  the mod's in-memory approval resists that, because it lives in state the
  agent's file access cannot write.
- It checks structure, not truth. A sourced fact can still be wrong; source
  records carry URLs and read dates so you can check them.
- It does not rate-limit itself. The skills cap gate calls per turn and
  redraft at most once before escalating, which is the standing mitigation
  for probing: enough guesses against the floor comparison could triangulate
  the number, so a dedicated probe counter is on the TODO list.
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
