# betterterms-mod

An opt-in Claude Code mod for betterterms. It ships with the marketplace
but nothing installs it until you ask for it:

```
claude plugin install betterterms-mod@betterterms
```

It assumes the core `betterterms` plugin is installed too: the pre-send
guard shells out to `betterterms-guardrails/scripts/bt.py`, resolved as
a sibling plugin dir first and as the repo `skills/` dir when the mod
runs in place from the repository.

## What it does

- **Pane** (`id: betterterms`): a cockpit with three tabs. `1 Cases`
  draws one card per case with its pipeline stage (`found`,
  `researched`, `in exchange`, `waiting`, `closed`), next action, and
  for the selected case the six-step strip and the offer bar from
  `plan.yaml` (start, their offer, target; the walk-away never shows).
  `2 Approvals` counts held drafts in its label and draws one card per
  held draft: the rendered text with the money spans lit, the gate's
  reasons, and Approve and send (`a`), Edit (`e`), Reject (`r`) on the
  top card. `3 Savings` shows the ledger's `saved_per_year` totals per
  currency, one-time savings as `$N once`, plus a cumulative chart.
  Opens itself at session start when
  cases exist; `/betterterms` or `/betterterms-cases` reopens it.
- **AbovePrompt band**: `Comcast replied, 1 draft waiting` while a
  reply is unanswered or a draft waits (held, or a `gate.json` verdict
  of `pass`/`needs_approval` not yet logged in `thread.md`). The
  Review button (hotkey `2`, the tab it opens) jumps to Approvals.
- **Status line**: `bt: <n> cases · $<saved>/yr saved`, refreshed by
  the poll; mixed currencies list each total separately, and one-time
  savings trail as `· $<n> once`.
- **Toasts**: `New reply in <case>.` when `thread.md` gains an inbound
  entry, `draft ... sent` when the guard lets a send through, and
  `draft ... blocked` when the gate refuses. Polled every 3 s.
- **Gate rows**: a `bt.py gate` tool row in the transcript is redrawn
  as `✓ Gate pass`, `✗ Gate block: <reason>` or `● Held for you`.
- **Pre-send guard**: a `tool.call` hook. When a call's arguments carry
  an open case's last `gate.json` `rendered` text, the mod runs
  `python3 <core plugin>/skills/betterterms-guardrails/scripts/bt.py gate`
  and enforces the verdict: `block` or a gate error denies the call,
  `pass` follows autonomy (1 denies, 2 asks, 3 and 4 allow), and
  `needs_approval` denies to the pane with
  `held for your approval in the BetterTerms pane (draft <hash8>)`.
  A thrown hook denies too; nothing fails open.

## The approval flow

`needs_approval` means the draft sits in `cases/<id>/held/<hash>.yaml`
and only a press can move it. The guard never asks inline and never
records anything for the agent's own call. The flow is:

1. The Approve press runs `bt.py held approve <case> <hash8>` through
   `$.process.run`, which writes `held/<hash>.approved` on disk and
   returns the full hash.
2. The press records that full hash under `$.state` key
   `betterterms-mod/approvals` (session only, never a file the agent
   can write) and submits a prompt asking the agent to send the same
   text.
3. The resend re-runs the gate, gets `needs_approval` again, finds the
   hash in `$.state`, consumes it, and re-gates once with
   `--approved`. If an agent-side `gate --approved` already spent the
   marker, the mod re-arms it first so the send cannot deadlock. If
   the re-gate does not spend the marker, the mod removes it again
   with `bt.py held disarm`. The `$.state` entry is spent on read and
   the marker on use, so a second identical send holds again. A typed
   `bt approve` works too: the mod's own `prompt.submit` hook resolves
   the hash through `held list` and records it in `$.state`. A
   `.approved` marker on disk never counts by itself; only `$.state`
   authorizes the send.
4. Different rendered text hashes to a different value, so an edited
   draft must re-pass the gate and be re-approved.

Reject runs `bt.py held reject <case> <hash8>`, which drops the held
draft and appends `## rejected <time> <hash>` to `thread.md`. The mod
reads those markers as markers, not turns. Edit opens an `Input`;
saving rewrites `draft.yaml` with the new text and re-runs the gate,
so the card re-lists under the new hash only after the gate sees it.

## What it reads and writes

Only `$BETTERTERMS_HOME` (default `~/.betterterms`): `cases/<id>/` names
matching `[a-z0-9-]+` (linked dirs skipped), `brief.yaml`, `thread.md`,
`draft.yaml`, `gate.json` (the verdict `bt.py gate` last wrote),
`plan.yaml` (target and the counterparty's amounts for the offer bar),
`inbound.yaml` existence for the gate's `--inbound` flag, `held/` for
the approval cards, `sources/` listing for the researched stage, and
`ledger.jsonl`. `.floor` is never read: the floor stays inside the
gate.

The writes: an Edit save rewrites `draft.yaml`, and the `held`
approve/reject subprocesses maintain `held/` and `thread.md` through
`bt.py`. Approval state lives in `$.state` for the session and inbound
baselines in module memory. The only other filesystem touch is a
`stat` resolve on a tool call's own `file_path` when one is present,
to tell a bookkeeping write inside a case dir apart from a send.

The scan caches each case's parsed form on a fingerprint of its files
(inode, mtime and size; held/ and sources/ on entry names), and UI
renders may reuse a snapshot for 250 ms so a
drag or redraw storm stats the tree once. A case whose held list
could not run is never cached. The pre-send guard never
uses the burst: it stats fresh and re-runs the gate anyway.

## What "send" means

There is no dedicated send tool; the mod treats a call as a send from
an open case when a normalized copy of the `rendered` text in the
case's `gate.json` appears inside one of its string arguments (for
renders under 24 chars the call must also name the case id). A send
then passes only when the gate is re-run on the draft on disk and one
string argument equals the freshly rendered text exactly, with the
other string arguments limited to envelope fields (recipient, subject,
channel ids): extra message body is denied, and an edited draft is
denied until it is re-gated. It covers `Bash` commands, MCP tool
arguments and agent prompts alike. Writes whose target resolves inside
the case dir (`draft.yaml`, `inbound.yaml`, `gate.json`, `thread.md`
bookkeeping) are excluded. Known holes, by design at v1: a send that
reads the rendered text indirectly (`cat gate.json | mail ...`)
carries no text to match, and a paraphrased render is not the render.
The guard protects the normal flow; it is not a sandbox.

## The mod API this relies on

Claude Code 2.1.288, plugin-authoring skill reference (the API is
marked early access and is version-specific):

- A function-hook plugin carries `hooks/hooks.json` with `modules`.
  Paths resolve relative to `hooks/`, so a root `register.js` is named
  `"../register.js"`.
- A hooks module exports `register(on)`; `on(event, matcher?, hook)`
  with hooks `($, e, next)`. `next(e)` defers to other plugins and the
  engine's own behavior. `on(...).catch(fn)` runs when the hook threw;
  the send guard's catch denies any call that still looks like a send.
- `tool.call` hooks may return `{ deny: reason }` to refuse the call,
  which is how the pre-send guard blocks. This is the mods-side answer
  to the classic `PreToolUse` shape.
- `ui.render` hooks match `{ component: "AbovePrompt" }`,
  `{ component: "Pane", requestId }` and `{ component: "ToolUse" }`.
  Elements come from `$.ui.resolve(e)` (`Box`, `Text`, `Button`,
  `Input`, ...) and are built with the ambient `h(tag, props,
  ...children)` factory (JSX compiles to it).
- `$.ui.open({ id, title })` mounts a pane; `$.ui.toast(text)` shows a
  toast; `$.ui.ask(question, { options, header })` resolves to the
  chosen label; `$.ui.notice(tool_use_id, text)` annotates an open
  dialog; `$.ui.status(text)` sets the status line;
  `$.ui.invalidate("ui.render")` redraws.
- `$.state.get|set(ref)` holds session values named in
  `types/index.d.ts`; `$.prompt.submit({ text })` queues the resend
  after a press.
- `$.fs.read|list|stat|exists|write`, `$.process.run(argv, { env,
  timeoutMs })` (argv vector, no shell), `$.env.get(name)` (the names
  are recorded by validation), `$.clock.every(ms, fn)` (returns a
  cancel), and `$.command.register({ name, description })` are the host
  calls used.
- The loader constrains hook modules: `$` may reach only top-level
  declared functions, dynamic `import()` is refused, and Node builtins
  are not available. That is why all parsing lives in `lib/cases.js`
  and `lib/approvals.js` (pure functions, unit-tested under
  `node --test`) and state is module-scoped.

## Tests

```
cd mod && node --test               # unit tests, no installs
claude plugin test ./mod            # engine-side tests (*.test.tsx)
claude plugin validate --strict ./mod   # manifest + hooks module audit
```

`register.test.tsx` and `approvals.test.tsx` are `.tsx` only so
`node --test` skips them: node can strip types from `.ts` but cannot
resolve `claude-code/testing`, which exists solely inside the Claude
test runner. The bare `node --test mod` form is Node-version specific;
running it inside `mod/` works everywhere.
