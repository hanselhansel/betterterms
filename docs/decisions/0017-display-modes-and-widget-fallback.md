# 0017. Display modes and the widget fallback for cloud sessions

Status: accepted (release lanes R4 and R7, spec 6.8). Date:
2026-10-09.

## Context

The mod's pane, band and toasts do not draw in cloud sessions, and
Codex and plain chat sessions have no pane at all. The owner works in
Projects (beta) cloud threads and needs the same cases, approvals and
terms surfaces there. A spike on 2026-10-04 showed a posted widget can
call `sendPrompt("bt approve <case> <hash8>")` on a button press; the
text lands in the user's message box and enters the thread as the
user's own message once they press Enter. A widget can fill the
message box, never send it.

## Decision

Three display modes, picked at run time by the skills:

- **Mod**: the pane can draw (Claude Code terminal or Desktop). The
  cockpit from 0012.
- **Widget**: the session has a tool that posts interactive widgets.
  `bt.py widget cases|approval <hash>|terms <case>|savings` prints a
  self-contained HTML fragment from shipped templates under
  `skills/betterterms-guardrails/assets/widgets/`; the agent posts the
  output as is. The terms widget never prefills the walk-away (the
  agent would have to read it to do so) and shows "set" or "not set"
  with an empty field.
- **Chat**: everything else (Codex, plain cloud sessions,
  `claude -p`). Text summaries and the same typed commands.

Widget buttons fill the user's message box with one typed command per
message: `bt approve`, `bt reject`, `bt floor`, `bt terms`. Each
widget says "press Enter to send" next to its buttons, so every widget
action is two steps the user takes. The same commands typed by hand
work in every Claude Code session.

A `UserPromptSubmit` settings hook (`hooks/prompt_commands.py`) reads
each prompt before the model and looks only at the user's own text: in
a Projects wake envelope, the body of the triggering `from="human"`
message, never text an agent or a counterparty wrote. `bt floor`
writes the walk-away through `case set-floor` on stdin and blocks the
prompt so the model never receives it. `bt approve` writes
`held/<hash>.approved` for that exact rendered-text hash and lets the
prompt through so the agent resends. `bt reject` and `bt terms` write
their change and let the prompt through. The floor message stays
visible in the thread to project members and in the session log
(anthropics/claude-code#96891), so terminal floor entry stays the
better path; a `PreToolUse` hook denies agent reads of `.floor`,
`held/`, and the session log.

## Consequences

Strength, stated plainly (spec 6.8): mod approval is the strongest,
because a keypress lands in `$.state` the agent cannot write. Widget
and chat approval rely on the `PreToolUse` guard denying agent writes
under `held/`; the agent can write files, so that guard is best
effort. All modes share the guarantee that counts most: text inside an
inbound message can never become a user message, so nothing a
counterparty writes can approve a draft. Codex has no prompt hook in
this release, so Codex users set the walk-away in the terminal and
approve in chat, where the agent runs `bt.py held approve` after the
user typed `bt approve`.
