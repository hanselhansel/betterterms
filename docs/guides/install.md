# Install

One repo serves every host. The skills live in `skills/` in the open Agent
Skills format; the packaging scripts generate each host's manifest from that
one tree. Pick your agent below.

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

Marketplace plugins do not load in cloud sessions. Two paths work:

- `python3 scripts/vendor-into-repo <repo>` copies the skills into
  `<repo>/.claude/skills/` and writes a `.betterterms-version` marker. Commit
  the result; the cloud session clones the repo and gets the skills with it.

In a Projects thread, the skills post the same views as interactive
widgets: cases, the approval card, the terms editor, savings. A widget
button fills your message box with a typed `bt` command; you press
Enter to send it. See the display modes table in
[quickstart](quickstart.md).

Cloud case folders are temporary. Treat a cloud case as short-lived: export
anything you want to keep before the session ends.

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
