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

- **Pane** (`id: betterterms`): one row per case with its pipeline
  stage (`found`, `researched`, `in exchange`, `waiting`, `closed`) and
  next action, plus the ledger's `saved_per_year` total. Opens itself at
  session start when cases exist; `/betterterms-cases` reopens it.
- **AbovePrompt band**: `N drafts waiting to send` while any open case
  holds a draft whose last `gate.json` verdict is `pass` or
  `needs_approval` and whose send is not yet logged in `thread.md`.
- **Toast**: `New reply in <case>.` when `thread.md` gains an inbound
  entry; polled every 3 s.
- **Pre-send guard**: a `tool.call` hook. When a call's arguments carry
  an open case's last `gate.json` `rendered` text, the mod runs
  `python3 <core plugin>/skills/betterterms-guardrails/scripts/bt.py gate`
  and enforces the verdict: `block` or a gate error denies the call,
  `needs_approval` always asks and re-gates with `--approved`, `pass`
  follows autonomy (1 denies, 2 asks, 3 and 4 allow).

## What it reads

Only `$BETTERTERMS_HOME` (default `~/.betterterms`): `cases/<id>/` names
matching `[a-z0-9-]+` (linked dirs skipped), `brief.yaml`, `thread.md`,
`draft.yaml`, `gate.json` (the last verdict the exchange skill saved),
`inbound.yaml` existence for the gate's `--inbound` flag, `sources/`
listing for the researched stage, and `ledger.jsonl`. `plan.yaml` and
`.floor` are never read: the floor stays inside the gate. The only
other filesystem touch is a `stat` resolve on a tool call's own
`file_path` when one is present, to tell a bookkeeping write inside a
case dir apart from a send. Nothing is written; inbound baseline state
lives in module memory for the session.

## What "send" means

There is no dedicated send tool; the mod treats a call as a send from
an open case when a normalized copy of the `rendered` text in the
case's `gate.json` appears inside one of its string arguments (for
renders under 24 chars the call must also name the case id). It covers
`Bash` commands, MCP tool arguments and agent prompts alike. Writes
whose target resolves inside the case dir (`draft.yaml`,
`inbound.yaml`, `gate.json`, `thread.md` bookkeeping) are excluded.
Known holes, by design at v1: a send that reads the rendered text
indirectly (`cat gate.json | mail ...`) carries no text to match, and
a paraphrased render is not the render. The guard protects the normal
flow; it is not a sandbox.

## The mod API this relies on

Claude Code 2.1.288, plugin-authoring skill reference (the API is
marked early access and is version-specific):

- A function-hook plugin carries `hooks/hooks.json` with `modules`.
  Paths resolve relative to `hooks/`, so a root `register.js` is named
  `"../register.js"`.
- A hooks module exports `register(on)`; `on(event, matcher?, hook)`
  with hooks `($, e, next)`. `next(e)` defers to other plugins and the
  engine's own behavior.
- `tool.call` hooks may return `{ deny: reason }` to refuse the call,
  which is how the pre-send guard blocks. This is the mods-side answer
  to the classic `PreToolUse` shape.
- `ui.render` hooks match `{ component: "AbovePrompt" }` and
  `{ component: "Pane", requestId }`. Elements come from
  `$.ui.resolve(e)` (`Box`, `Text`, `Button`, ...) and are built with
  the ambient `h(tag, props, ...children)` factory (JSX compiles to it).
- `$.ui.open({ id, title })` mounts a pane; `$.ui.toast(text)` shows a
  toast; `$.ui.ask(question, { options, header })` resolves to the
  chosen label; `$.ui.notice(tool_use_id, text)` annotates an open
  dialog; `$.ui.invalidate("ui.render")` redraws.
- `$.fs.read|list|stat|exists`, `$.process.run(argv, { env, timeoutMs })`
  (argv vector, no shell), `$.env.get(name)` (the names are recorded by
  validation), `$.clock.every(ms, fn)` (returns a cancel), and
  `$.command.register({ name, description })` are the host calls used.
- The loader constrains hook modules: `$` may reach only top-level
  declared functions, dynamic `import()` is refused, and Node builtins
  are not available. That is why all parsing lives in `lib/cases.js`
  (pure functions, unit-tested under `node --test`) and state is
  module-scoped.

## Tests

```
node --test mod/register.test.js     # unit tests, no installs
claude plugin test ./mod             # engine-side tests (register.test.tsx)
claude plugin validate ./mod         # manifest + hooks module audit
```

`register.test.tsx` is `.tsx` only so `node --test` skips it: node can
strip types from `.ts` but cannot resolve `claude-code/testing`, which
exists solely inside the Claude test runner.
