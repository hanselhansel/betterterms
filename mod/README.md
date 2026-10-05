# betterterms-mod

An opt-in Claude Code mod for betterterms. It ships with the marketplace
but nothing installs it until you ask for it:

```
claude plugin install betterterms-mod@betterterms
```

It assumes the core `betterterms` plugin is installed too: the cockpit
shells out to `betterterms-guardrails/scripts/bt.py`, resolved as a
sibling plugin dir first and as the repo `skills/` dir when the mod
runs in place from the repository.

The mod is a cockpit only (decision 0020): it registers no `tool.call`
or `prompt.submit` hook and never inspects outgoing tool calls or
prompts. Approval enforcement lives in `bt.py` itself: the gate's
hash-bound one-use `--approved` marker, in every mode.

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
  entry. Polled every 3 s.
- **Gate rows**: a `bt.py gate` tool row in the transcript is redrawn
  as `✓ Gate pass`, `✗ Gate block: <reason>` or `● Held for you`.

## The approval flow

`needs_approval` means the draft sits in `cases/<id>/held/<hash>.yaml`
waiting for you. The Approve press (`a` or click) does two things:

1. It runs `bt.py held approve <case> <hash8>` through
   `$.process.run`, which writes `held/<hash>.approved`, the marker
   bound to the SHA-256 of the send tuple. `held approve` refuses a
   hash that is not the case's current `gate.json` hash, so a stale
   card can never approve the new text.
2. It submits a prompt telling the agent to run `bt.py gate <case>
   --approved` exactly once and send the returned rendered text
   verbatim as its own argument, nothing added.

The gate spends the marker atomically on that run: a second
`--approved` call holds the draft again, and different rendered text
hashes differently, so an edited draft must re-pass the gate and be
re-approved. Consent is the marker alone; the mod records nothing in
`$.state` for approvals.

Reject runs `bt.py held reject <case> <hash8>`, which drops the held
draft and appends `## rejected <time> <hash>` to `thread.md`. The mod
reads those markers as markers, not turns. Edit opens an `Input`;
saving drops the old held record quietly (`bt.py held drop`, no thread
marker), rewrites `draft.yaml` with the new text and re-runs the gate,
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
approve/reject/drop subprocesses maintain `held/` and `thread.md`
through `bt.py`. Inbound baselines live in module memory; `$.state`
holds only the pane's tab and selected case.

The scan caches each case's parsed form on a fingerprint of its files
(inode, mtime and size; held/ and sources/ on entry names), and UI
renders may reuse a snapshot for 250 ms so a
drag or redraw storm stats the tree once. A case whose held list
could not run is never cached.

## The mod API this relies on

Claude Code 2.1.288, plugin-authoring skill reference (the API is
marked early access and is version-specific):

- A function-hook plugin carries `hooks/hooks.json` with `modules`.
  Paths resolve relative to `hooks/`, so a root `register.js` is named
  `"../register.js"`.
- A hooks module exports `register(on)`; `on(event, matcher?, hook)`
  with hooks `($, e, next)`. `next(e)` defers to other plugins and the
  engine's own behavior.
- `ui.render` hooks match `{ component: "AbovePrompt" }`,
  `{ component: "Pane", requestId }` and `{ component: "ToolUse" }`.
  Elements come from `$.ui.resolve(e)` (`Box`, `Text`, `Button`,
  `Input`, ...) and are built with the ambient `h(tag, props,
  ...children)` factory (JSX compiles to it).
- `$.ui.open({ id, title })` mounts a pane; `$.ui.toast(text)` shows a
  toast; `$.ui.status(text)` sets the status line;
  `$.ui.invalidate("ui.render")` redraws.
- `$.state.get|set(ref)` holds session values named in
  `types/index.d.ts`; `$.prompt.submit({ text })` queues the
  gate instruction after an Approve press.
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
