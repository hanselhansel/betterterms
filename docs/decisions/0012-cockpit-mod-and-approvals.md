# 0012. Cockpit mod and approvals by key or click

Status: accepted (release lanes R5 and R6, spec 6.1 to 6.7). Amends
0007: the walk-away may also be set and shown in the pane; entry still
never passes through the agent. Amended by 0020: the `tool.call` send
check and the `$.state` approvals described below are removed; the
press runs `held approve` and the prompt sends the agent through
`gate --approved` once. Date: 2026-10-08.

## Context

Claude Code mods can draw a pane, a band above the prompt, a status
line, toasts, and rewritten tool rows. The release needs a place the
user sees held drafts and acts on them without typing commands, and a
terms editor that sets the walk-away without the value passing through
a chat message or argv. A hook may not wait on its own promise past 10
seconds, and a timed-out hook is skipped, so the mod can never hold a
send open while it waits for the user.

## Decision

Ship `betterterms-mod` as a separate opt-in plugin in the same
marketplace, never required by the core kit:

- Pane on `/betterterms` with tabs 1 Cases, 2 Approvals (count badge),
  3 Savings. Cases shows stage, offer bar, the six-step progress
  strip, and a note per case; `t` opens the terms editor, `n` starts a
  new case. Savings reads `bt.py ledger total --json` and draws the
  cumulative line plus a bar per closed case.
- Band above the prompt appears only while something waits on the
  user, with a Review button. Gate tool rows redraw as one line
  (`pass`, `block: reason`, `held`). Toasts fire on replies, sends and
  blocks. The status line shows `bt: N cases · $X/yr saved`.
- Approvals tab lists one card per held draft in arrival order: full
  rendered text with new numbers highlighted, the gate's reasons, each
  check as pass or warning, and Approve (`a`), Edit (`e`), Reject
  (`r`). An edited draft must re-pass the gate before Approve works.
- Approval flow (security invariant, spec 6.3): on `needs_approval`
  the `tool.call` hook denies the send, records the held draft (case
  id, rendered text, SHA-256) in `$.state`, and shows the band. A
  press on Approve writes the approval for that exact hash in
  `$.state` and submits a prompt so the agent resends. On the resend
  the hook recomputes the hash of the new text; a matching unused
  approval runs the gate with `--approved`, anything else denies. The
  hook's `.catch` denies, so a failed or timed-out hook never lets a
  send through.
- Approvals live in `$.state` only. The agent can write files but
  cannot write `$.state`, so no file it creates and no text inside a
  counterparty message can approve a draft. Typing "yes" in chat
  approves nothing while the mod is loaded.
- Held drafts also persist as `held/<hash>.yaml` in the case folder,
  so a restarted session rebuilds the Approvals tab from files. Only
  the approval itself stays session-bound in `$.state`.
- Terms editor (`t` on a case): one scale, three draggable or
  typeable handles (target, best alternative, walk-away) plus the
  offer as a fixed marker. Save writes target and best alternative to
  `plan.yaml` and the walk-away through `bt.py case set-floor` on
  standard input, never in argv. The pane shows the walk-away plainly
  to the user (owner, 2026-10-04); the pane is drawn for the user and
  is not sent to the model.
- The mod parses no business rules: every gate, floor and ledger
  action runs `bt.py` through `$.process.run`; files are read through
  `$.fs`. It reads only `~/.betterterms`.
- `claude plugin test` covers pane, band, approval, edit-rerun,
  changed-text deny, forged-approval ignore, throwing-gate deny,
  stdin-only floor write, and drag fields, run on `terminal` and
  `desktop`. `node --test` suites stay.

## Consequences

The core kit works identically with or without the mod; the mod only
changes who sees what and how approval is recorded. Mod approval is
the strongest path the kit offers because no file the agent can write
carries it. Pane, band and toasts do not draw in cloud sessions; the
widget fallback (0017) covers those. The 10-second hook limit is met
by construction: the hook returns at once after holding the draft, and
the draft itself waits in files for as long as the user takes.
