# Quickstart

Two journeys cover the kit: Act for written exchanges, Coach for live
conversations. Both start the same way: a command, a short intake, and a
walk-away number you set yourself.

## Journey 1: lower a subscription (Act)

1. Run `/betterterms:subscriptions`. Not sure which pack fits? Run
   `/betterterms` and say what you want to improve. In Codex there are
   no slash commands: name the skill instead (`betterterms-start`
   routes you, `betterterms-subscriptions` starts the pack).
2. Intake asks what a good result looks like, what the worst deal you
   would still take is, what it may never disclose, your deadline, and
   how much autonomy it gets. It ends with a ranking check: you order
   three sample outcomes so it can confirm it read your priorities
   right.
3. Set your walk-away number, once per case. Where you set it depends
   on your session:

   - Any terminal: run the `case set-floor` command the skill prints
     (it resolves the full `bt.py` path for you). It prompts
     `Walk-away number (hidden): ` and does not echo.
   - Claude Code with the `betterterms-mod` plugin: the terms editor
     in the BetterTerms pane (`t` on the case) sets it by drag, nudge,
     or a typed field.
   - A Projects cloud thread: the terms widget's walk-away field
     types `bt floor <case_id> <amount>` into your message box; you
     press Enter and the prompt hook writes it. The value stays
     visible in the thread, so the terminal is the better path when
     you have one.
   - Any chat surface: type `bt floor <case_id> <amount>` yourself.
     The prompt hook writes it and blocks the message, so the model
     never receives it.

   The value lands in a `.floor` file only the gate and the scorer
   read. The model never sees it and the chat never repeats it.
4. Discovery says what it wants to read (receipts, renewal notices,
   price-change mail, any statements you drop in) and asks permission
   per source. It returns a target list: counterparty, amount, period,
   renewal date, evidence, usage signal.
5. Pick the targets. Each pick becomes its own case with its own
   walk-away: a case never holds more than one counterparty. Research
   reads each vendor's cancellation, refund, and pricing policy, current
   promotions, recent first-hand reports, and your rights. Every fact
   lands in a source record with a URL and the date read.
6. Plan gives you the target price, two or three equal options, and a
   concession ladder. The floor stays in code.
7. Exchange drafts each message in your voice. At the default autonomy
   every send waits for you. When the gate holds a draft, you get the
   rendered text and the plain-word reasons, then approve or reject it
   (how depends on your display mode, below). Inbound replies get
   parsed, scored against your priorities, checked against the fact
   list, and answered.
8. Accept, cancel, pay, sign, and dispute always wait for your explicit
   approval. When the case closes, the ledger records the saving.
   `bt.py ledger total` answers "how much have I saved".

## Journey 2: negotiate a job offer (Coach)

1. Run `/betterterms:salary` (`betterterms-job-offer` in Codex).
2. Intake captures the full offer (base, bonus, equity type and vesting,
   level, start date), the deadline, your other processes, your
   priorities, and your walk-away number through the same paths as
   above. Default autonomy is level 1: drafts only, you speak.
3. Discovery reads the offer letter and recruiter emails only if you
   allow it.
4. Research gathers comp data, the company's leveling and policies, and
   recent negotiation reports. Comp numbers come from what you supply
   plus cited public sources.
5. Plan fixes the ask, the package, and the trade-offs before any call.
   You commit to the numbers here, not mid-conversation.
6. Coach writes your call script: the opening line, the ask as a precise
   figure, your reasons, two or three equal package options, answers to
   the five likeliest objections, and the closing request to get it in
   writing.
7. Rehearse. The agent plays the recruiter with realistic pushback, then
   scores your delivery against the script.
8. Have the live conversation. Then debrief: what was offered, an
   updated plan, and a drafted follow-up email. The ledger records
   final versus initial package.

## Held drafts

When the gate returns `needs_approval`, nothing has left: the draft is
held on disk as `held/<hash>.yaml` in the case folder, and the gate's
answer carries the `hash`. You approve the exact rendered text, not a
draft in general: your approval is a file named after the SHA-256 of
that text, and the gate consumes it after one send. Edit the draft and
the old approval no longer matches, so the new text is held again.
Held drafts survive restarts, so the same list is waiting in a later
session.

## The four typed commands

One command per message, wherever you type to the agent. A
`UserPromptSubmit` hook reads it before the model does.

| Command | What it does |
|---|---|
| `bt approve <case_id> <hash8>` | Approves the held draft with that hash. The hook writes the approval and lets the prompt through with a note, so the agent resends the same text. |
| `bt reject <case_id> <hash8>` | Drops the held draft and stamps `rejected` in `thread.md`. |
| `bt floor <case_id> <amount>` | Writes the walk-away on stdin to `case set-floor`, then blocks the message so the model never receives it. |
| `bt terms <case_id> target=<amount> alternative=<amount>` | Writes target and best alternative to `plan.yaml`. Either key alone works, in any order. |

Amounts accept `62`, `62.50`, `$62`, `1,200`. `hash8` is the first 8
hex characters of the draft's hash, shown on the approval card or in
the printed text.

## The three display modes

The skills pick one at run time. What each mode gives you, stated
plainly:

| Mode | When | What it guarantees |
|---|---|---|
| Mod | Claude Code terminal or Desktop with `betterterms-mod` installed | The cockpit: a pane with Cases, Approvals, and Savings tabs, a band over the prompt when a draft waits, toasts on replies, and one-line gate rows. Approval is your keypress or click, recorded in mod state the agent cannot write. Typing "yes" in chat approves nothing here. |
| Widget | A session with a tool that posts interactive widgets (Projects cloud threads) | The same views as posted widgets. A button fills your message box with the typed command; you still press Enter, so every action is yours. Approval lands as a `held/<hash>.approved` file the prompt hook writes. |
| Chat | Codex, plain cloud sessions, `claude -p` | Text summaries and the same typed commands. Where the session has no prompt hook, the agent runs `bt.py held approve` itself after you reply `bt approve`. |

The honest line on strength: mod approval is the strongest, because a
keypress lands in state the agent can never write. Widget and chat
approval rely on the `PreToolUse` hook that denies agent writes under
`held/`; it is best effort, since the agent can write files. All three
modes share the guarantee that counts: text inside a counterparty's
message can never become a user message, so nothing the other side
writes can approve a draft.

## What a turn looks like in Act mode

Each inbound message produces `inbound.yaml` (the counterparty's offer,
its text, the amounts it stated). The scorer bands the offer against
your target and floor. The agent picks one move, writes `draft.yaml`
with a template and placeholders instead of typed prices, and runs
`bt.py gate`. On `pass` the rendered text is what goes out, verbatim.
On `block` it redrafts once or escalates. On `needs_approval` the draft
is held for your decision, per the modes above.
