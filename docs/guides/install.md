# Install

One repo serves every host. The skills live in `skills/` in the open Agent
Skills format; the packaging scripts generate each host's manifest from that
one tree. Pick your agent below.

Platforms: macOS, Linux, or WSL. `bt.py` uses Unix file locking, so
native Windows is unsupported and `scripts/doctor` reports it.

## Claude Code (terminal and desktop)

Inside Claude Code:

```
/plugin marketplace add hanselhansel/betterterms
/plugin install betterterms@betterterms
```

Auto-update is off for third-party marketplaces until you turn it on. Without
it you stay on the installed version until you update by hand.

`/betterterms` routes you to a pack. `/betterterms:<command>` starts one
directly (`subscriptions`, `cancel`, `refunds`, `bills`, `ai-api`, `salary`,
`promotion`).

## Claude Code cloud sessions

A cloud session never installs the plugins a repo's
`.claude/settings.json` declares under `enabledPlugins`, including
marketplaces listed under `extraKnownMarketplaces`. What a cloud
session does read: skills under `.claude/skills/` in every case, and
a repo's `hooks` and permission rules when the session has exactly
one repository. Two paths cover cloud sessions:

- **Projects threads**: add betterterms under Project settings >
  Plugins from the `hanselhansel/betterterms` marketplace, then
  start a new thread. Changes to project plugins reach new threads,
  never a running one.
- **A plain cloud session or a single-repo project**: run
  `python3 scripts/vendor-into-repo <repo>` and commit the result.
  It vendors the skills into `<repo>/.claude/skills/` (with a
  `.betterterms-version` marker), copies the hook scripts into
  `<repo>/.claude/betterterms/hooks/` (with its own marker), and
  merges `UserPromptSubmit` and `SessionStart` entries into
  `<repo>/.claude/settings.json` with `$CLAUDE_PROJECT_DIR` paths.
  Existing keys are kept and entries are never duplicated. The
  vendored hooks apply only in a session with one repository, so a
  multi-repo project must use Project settings > Plugins instead.
- `python3 scripts/vendor-into-repo --no-hooks <repo>` vendors only
  the skills. No prompt hook runs then, so a typed `bt` command
  reaches the model as ordinary chat text; the terminal
  `case set-floor` command is the only safe floor path there.

Hooks load at session start. Installing the plugin mid-session
activates the typed-command hook at the next session start
(`/reload-plugins` locally); until then a typed `bt floor` reaches
the model.

In a Projects thread, the skills post the same views as interactive
widgets: cases, the approval card, the terms editor, savings. A widget
button fills your message box with a typed `bt` command; you press
Enter to send it. See the display modes table in
[quickstart](quickstart.md).

Cloud case folders are temporary. A case in a cloud session's home
folder vanishes when the VM ends; the session-start hook prints a
one-line warning when the betterterms home sits somewhere ephemeral
and already holds a case.
Treat a cloud case as short-lived: export anything you want to keep
before the session ends.

## Codex

```
codex plugin marketplace add hanselhansel/betterterms
codex plugin add betterterms@betterterms
```

Codex has no slash commands: name the skill instead. Ask for
`betterterms-start` and it routes you, or name a pack skill directly
(`betterterms-subscriptions`, `betterterms-bills`,
`betterterms-refunds`, `betterterms-cancellations`,
`betterterms-ai-api`, `betterterms-job-offer`,
`betterterms-promotion`). Codex also has no prompt hook in this
release: you set the walk-away with the `bt.py case set-floor`
terminal command, and approve held drafts by typing `bt approve
<case_id> <hash8>` in chat.

## Other Agent Plugins readers

The repo root carries an Agent Plugins 1.0 `plugin.json` that points at
`skills/`. Add the repo as a plugin source in your host.

## Any Agent Skills reader

```
python3 scripts/install-skills --target ~/.agents/skills
```

This links each `skills/betterterms-*` folder into the target directory
(`--copy` copies instead of linking). It refuses when the same skill exists in
both `~/.agents/skills` and `~/.claude/skills`, so a skill never loads twice.
Point any other reader at `skills/` directly.

## The optional mod

`betterterms-mod` is a separate Claude Code plugin in the same marketplace:

```
/plugin install betterterms-mod@betterterms
```

It adds a pane with Cases, Approvals, and Savings tabs, a band above the
prompt when a draft waits for you, one-line gate rows in the transcript,
and toasts on new counterparty replies. Its terms editor sets the
walk-away without typing it in a terminal. It reads only
`~/.betterterms`. The core kit never depends on it. Its pane, band and
toasts do not draw in cloud sessions; the widget fallback covers those.

## Keeping installs honest

```
python3 scripts/doctor
```

Run from a clone of this repo, doctor scans `~/.agents/skills` and
`~/.claude/skills` and reports broken links, the same skill installed in both
folders, and versions that do not match the repo's `VERSION`. It prints one
line per finding and exits 1 when anything is wrong.

## Uninstall

Remove the plugin through your host's plugin command, or delete the linked
`betterterms-*` entries from `~/.agents/skills` and `~/.claude/skills`. Your
cases in `~/.betterterms` are plain files; delete the folder to remove them.
