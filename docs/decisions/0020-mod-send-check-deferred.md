# 0020. Mod send check deferred: the mod ships as a cockpit only

Status: accepted. Amends 0012, 0017, 0018 and 0019. Date: 2026-10-10.

## Context

The mod's pre-send check hooked `tool.call`, matched outgoing calls
against each case's gated text, re-ran the gate, and enforced the
verdict: a held draft passed only with an approval recorded in
`$.state`, a pass followed the case's autonomy, a block denied.
Four review rounds hardened it and four reviews still rejected it:

- Round one bound the consent record to the send tuple (action,
  offer, period, currency, rendered text) and spent it once.
- Round two moved consent off disk entirely: a pane press wrote only
  `$.state`, which the agent cannot write, and the `.approved` file
  became only what `gate --approved` spends, with `held disarm` to
  clear a re-armed marker the re-gate did not use.
- Round three replaced pattern matching with one strict send shape:
  the gated text verbatim as its own argument beside delivery
  metadata only, a shell command never a send.
- Round four made the shape default-deny by key class and refused an
  approval whose hash was not the case's current `gate.json` hash.

Each round answered the last review's objection and raised the next
one. The shape loose enough to admit the connectors a user actually
sends through (mail, chat, MCP calls that wrap the text, id fields
of every name) is the same shape that admits a padded or dressed-up
send; tightening it broke real sends, loosening it let forged ones
through. The check also re-ran the gate on every matching call,
which sits badly under the 10-second hook budget, and it could only
ever guess that a call was a send: a file write carrying the text is
not one, an unknown connector might be. Inspecting arbitrary
connector calls was the wrong boundary.

## Decisions

- The `tool.call` send check leaves release 0.10.0: the hook and its
  `.catch`, the send matcher and shape rule, the `$.state`
  approvals, the re-arm and disarm wiring, the autonomy ask and the
  "draft sent" toast are all removed. `bt.py held disarm` goes with
  them; nothing else called it. The mod keeps its cockpit hooks:
  session.start, command.run, ui.render (pane, band, gate rows),
  inbound toasts and the status line. It registers no `tool.call`
  or `prompt.submit` hook and does not inspect outgoing tool calls
  or user prompts.
- Approval in the mod: pressing Approve runs `bt.py held approve
  <case> <hash8>` (which refuses a non-current hash) and submits a
  prompt telling the agent to run `bt.py gate <case> --approved`
  once and send the returned rendered text verbatim as its own
  argument. Reject runs `held reject`; Edit keeps `held drop` plus a
  re-gate. The gate's `--approved` marker, bound to the send-tuple
  hash and spent once, is the only approval enforcement, in every
  mode.
- The same-user limit stands plainly (0019): outside a separate OS
  user nothing technical stops a determined agent from writing an
  `.approved` marker, sending ungated text, or skipping the gate.
  The skills' rules, the gate's checks and the held list's hash
  verification bound honest mistakes, not a hostile agent.
- A betterterms-owned send tool is the future boundary (P1 TODO):
  sends go through a tool betterterms owns rather than inspecting
  arbitrary connector calls, so the check sees a call it can name
  and the gate verdict rides the one path a send can take.
