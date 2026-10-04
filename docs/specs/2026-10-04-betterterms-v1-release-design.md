# betterterms v1 release design (2026-10-04)

Status: approved by the owner 2026-10-04 (cloud widget path added the same day). Branch: `feat/release-v1` (steps 2 to 10, one PR).
Inputs: the design spec and negotiation procedure (2026-10-03), the v1 plan, decisions 0001 to
0011, `TODOS.md`, the release gap check (`docs/plans/2026-10-04-release-gap-check.md`), and the
owner's answers in the project thread on 2026-10-04.

## 1. Goal

Ship betterterms 0.10.0 as one release that a stranger can install and use end to end:
install the plugin, start a case, set their terms, approve or reject held drafts, and see what
they saved. Then make the GitHub repo public.

Success means all of these hold on the final commit:

1. `python3 scripts/verify` passes every check, including the mod tests.
2. Dev eval passes at least 9 of 12 cases. A separate agent runs the holdout and reports at
   least 10 of 12, and never shows its cases.
3. Install tests pass on the final branch for Claude Code (marketplace add, install, 10 skills
   listed, mod loaded), Codex (marketplace add, plugin add), and repo vendoring.
4. One real case runs end to end with the shipped files: intake, terms set in the pane, one
   held draft approved in the pane, gate pass, ledger entry. A second run does the same in a
   Projects cloud thread through widgets (section 6.8).
5. `/ship` and `/land-and-deploy` complete, the repo is public, and local and GitHub `main`
   point at the same commit.

## 2. Scope

### In

- Release blockers from the gap check (section 3).
- Core fixes (section 4).
- `~/.betterterms/config.yaml` (section 5).
- The cockpit mod for Claude Code terminal and Desktop (section 6).
- Version 0.10.0, CHANGELOG entry for steps 2 to 10, stale text scrubbed.

### Removed completely (owner, 2026-10-04)

Delete the code, manifests, verify checks, tests and doc mentions for:

- Per-country call and recording rules (`rules/jurisdictions/` mentions, the `jurisdiction`
  config key, pack `rights.md` lines that promise them).
- claude.ai skill zips (`scripts/zip-skills`, its tests and docs).
- Gemini, Cursor and Muse (`GEMINI.md`, `gemini-extension.json`, `scripts/_lib/gen_gemini.py`,
  `gen_cursor.py`, `gen_muse.py`, their generator entries, tests and install-guide sections).

Supported hosts after this release: Claude Code (plugin and mod), Codex (plugin), and any
agent that reads a vendored `skills/` folder.

### Deferred (recorded in a decision, not built)

- The 12 metrics in procedure spec section 8 and multi-turn simulated counterparties.
- The 14 pack eval cases (2 per pack). Evals stay at the current 12 cases.
- Response sharing (README line removed).

## 3. Release blockers

1. **Walk-away entry path.** The intake skill and quickstart tell the user to run
   `python3 ../betterterms-guardrails/scripts/bt.py case set-floor`, which only resolves inside
   the skill folder. Fix: every user-facing command prints an absolute path resolved at run
   time (`bt.py` reports its own path through `bt.py where`), and on Claude Code the pane's terms
   editor sets the walk-away directly (section 6.4).
2. **Evals rerun** on the final code (targets in section 1).
3. **Install tests** on the final branch (section 1, item 3).
4. **Dogfood case** (section 1, item 4).
5. **Publish**: one PR, then public on landing.

## 4. Core fixes

1. **Templates pass their own gate.** Shipped message templates must not trip review rules
   ("no longer works for me" contains "works for me"). Fix the phrases or the matcher, and add a
   verify check that renders every shipped template with sample case data and runs it through
   the gate at autonomy 3 and 4. Any `needs_approval` or `block` fails verify.
2. **One case per target.** Discovery can list several targets. After the user picks, intake
   creates one case per chosen target, each with its own walk-away. A case never holds more
   than one counterparty.
3. **Step 2 adversarial findings.** Confirm each against the release branch and fix any still
   open: `never_disclose` items with letters (`CHF 90`, `$85/month`) must block when they
   appear; an explicit `period: null` on an option or fact is an input error (exit 2); a blocked
   draft never shows "offer is at your limit"; ledger reads a nested line without recursion
   errors, appends with a leading newline when the file lacks one, and holds a lock across
   read and append.
4. **Quoting a counterparty's price** (open since step 2, 0008-E against 0010-A). A cancel or
   dispute draft may need to quote the price the counterparty charged, which can sit above the
   walk-away. Proposed rule: `{quote:n}` placeholders render inbound text verbatim and are
   checked against `never_disclose`, but amounts inside a quote are not offers and never meet
   the floor check. Amounts outside quotes keep every current rule. Approved by the owner
   2026-10-04.
5. **Mod tests in verify.** `scripts/verify` runs `node --test` for `mod/`, plus
   `claude plugin validate --strict mod` and `claude plugin test mod` when the `claude` binary
   is present. When the binary is absent, those two report `SKIPPED (claude not installed)`.
   They never report PASS.
6. **Stale text.** The design spec no longer says "not implemented" for built parts. No local
   home paths in shipped files (verify already checks). The packaging research's old name is
   corrected. README drops the response-sharing line. Root `plugin.json` gains the `skills` key
   the README describes. Codex docs name skills, not slash commands.

## 5. config.yaml

File: `~/.betterterms/config.yaml`, mode 0600, created by intake on first run if absent.

```yaml
autonomy: 2          # default autonomy level for new cases, 0 to 4
currency: USD        # default plan currency for new cases
sign_off: "Your Name" # name used to sign drafts
voice_notes: ""      # free text the drafting skills read, such as "short, friendly"
```

Rules:

- Intake reads it to prefill new cases. Values copy into `brief.yaml` and `plan.yaml` when a
  case is created, so changing config later never changes an existing case.
- Drafting skills read `sign_off` and `voice_notes`.
- The gate and the mod's approval path never read config. Everything the gate decides comes
  from the case files and the walk-away file.
- Unknown keys are ignored with a warning. A bad value (autonomy 7, currency "dollars") makes
  intake stop with a plain error naming the key.
- `bt.py config show` and `bt.py config set <key> <value>` read and write it.

## 6. The cockpit mod

The mod is a Claude Code plugin module under `mod/`, shipped as the opt-in `betterterms-mod`
plugin in the same marketplace as the core plugin.
Surfaces: terminal and Desktop get the full design. VS Code and mobile get the same tabs as
plain text and buttons with no charts. Codex has no mods and keeps the chat flow.

Docs basis: Claude Code mods reference and interface guide for v2.1.287, read 2026-10-04.
Limits that shape the design: a hook's own work is capped at 10 seconds, redraws are capped
at 10 per second on Desktop and 30 in the terminal, SVG is Desktop only (up to 131,072
characters, animated and hoverable when `isInteractive`), `Raster` is terminal only, mods
cannot bind the arrow keys, and a pane opens by itself only at 144 columns or wider.

### 6.1 Places it draws

| Place | What it shows |
| --- | --- |
| Pane (`/betterterms`) | Tabs 1 Cases, 2 Approvals (with a count badge), 3 Savings |
| Band above the prompt | Shown only when something needs the user: "Comcast replied, 1 draft waiting" with a Review button (digit hotkey) |
| Status line | `bt: 4 cases · $486/yr saved` |
| Toast | A reply arrived, a draft was sent, a draft was blocked |
| Gate rows in the transcript | Each `bt.py gate` tool row redrawn as one line: `✓ Gate pass`, `✗ Gate block: <reason>`, or `● Held for you` |

### 6.2 Cases tab

One card per case: counterparty, stage chip, and when selected an offer bar (start price,
their current offer, target), the six-step progress strip (Intake, Research, Draft, Sent,
Reply, Close), and a one-line note. Desktop draws the bar as animated SVG with hover values.
The terminal draws it with block characters. Up and down move between cases, Enter opens,
`t` opens the terms editor, `n` starts a new case.

### 6.3 Approvals tab

One card per held draft, in arrival order. Each card shows:

- the full rendered message, with new numbers highlighted,
- why it was held, in the gate's own words,
- each gate check as a pass or warning line,
- Approve and send (`a`), Edit (`e`), Reject (`r`). Mouse click and keypress both work.

Edit opens the draft text in an input field. Saving an edit re-runs the gate before the card
can be approved.

**How approval reaches the send** (security invariant). A hook may not wait on its own promise
past 10 seconds, and a hook that times out is skipped, which would let the send through. So
the mod never holds a send open while it waits for the user:

1. The agent's send tool call reaches the mod's `tool.call` hook. The mod runs the gate. On
   `needs_approval` it records the held draft (case id, rendered text, SHA-256 of the rendered
   text) in `$.state`, returns `{ deny }` telling the agent the draft is held for the user, and
   shows the band and the badge.
2. When the user presses Approve, the mod writes an approval for that exact hash into
   `$.state` and submits a prompt telling the agent the draft was approved and may be sent.
3. On the resend, the hook recomputes the hash of the newly rendered text. A matching,
   unused approval lets the call run the gate with `--approved`, then `next(e)`. Any change to
   the text, a second use, or a missing approval denies it again.
4. The hook has a `.catch` handler that denies the send. A failed or timed-out hook never
   lets a send through.

In mod mode, approvals live in `$.state` only. The agent can write files but cannot write `$.state`, so no
file it creates, and no text in a counterparty's email, can approve a draft. Typing "yes" in
chat does not approve a held draft while the mod is loaded.

**Held drafts never expire.** The 10-second limit applies to the hook, which returns at once
after holding the draft. The draft itself waits in the Approvals tab for as long as the user
takes: minutes, hours or days. Held drafts are also written to the case folder
(`held/<hash>.yaml`, rendered text plus gate reasons), so a new session rebuilds the
Approvals tab from files after Claude Code restarts. Only the approval itself lives in
`$.state`, so an approval always comes from a press in the current session. Nothing is sent
while nobody is there to press.

### 6.4 Terms editor

Opened with `t` on a case. One price scale with three handles: target (green), best
alternative (blue), walk-away (red), and the counterparty's current offer as a fixed marker.

- **Drag** with the mouse through a `Client` element (pointer down, move, up on terminal and
  Desktop). $1 steps.
- **Nudge**: Tab to a handle, then `-` or `+`.
- **Type**: a number field per handle, all three updated live by dragging.
- **Spacing**: the scale fits the values plus 25 percent padding (at least $4 each side) and
  re-fits on release, never during a drag. `z` toggles a full range. Target and walk-away labels
  sit above the bar and best alternative below, with leader lines. Labels that would overlap
  stack into a second row.
- **Checks shown as plain lines**: walk-away below target (the gate would block every offer
  hoped for), target and walk-away less than $3 apart (little room to trade), best alternative
  costs more than walk-away (consider raising it).
- **Save** (`s`) writes target and best alternative to `plan.yaml`, and writes the walk-away
  through `bt.py case set-floor` with the value on standard input, never in argv and never in
  any text the agent reads.

The walk-away value is shown plainly in the pane (owner, 2026-10-04). The pane is drawn for
the user and is not sent to the model. The agent still never reads the walk-away file and
never sees the value.

New field in `plan.yaml`:

```yaml
best_alternative:
  amount: 60
  period: month
  note: "Verizon quote, 2026-10-01"
```

Drafting skills may cite the note when the user allows it. The gate does not use it.

### 6.5 Savings tab

Total saved per year, a cumulative line chart by week (SVG on Desktop, `Raster` in the
terminal), one bar per closed case, and a summary line (closed, walked away, average
reduction). All numbers come from `bt.py ledger total --json`.

### 6.6 Data flow

The mod reads case folders under `~/.betterterms/cases/` with `$.fs` and runs `bt.py` through
`$.process.run` for every gate, floor and ledger action. It parses no business rules itself.
Pane state (selected tab, selected case) lives in `$.state`. Nothing the mod draws is
appended to the conversation, except the deny messages and the approval prompt in 6.3.

### 6.7 Tests

Every pane, band and approval behavior has a `claude plugin test` case, run once on
`terminal` and once on `desktop`:

- held draft shows in the band and the badge, Approve sends exactly once,
- an edited draft must re-pass the gate before Approve works,
- a resend with different text is denied,
- a forged approval file in the case folder is ignored,
- a throwing gate call denies the send,
- terms editor writes the walk-away through stdin and never puts it in argv,
- all three number fields follow a drag.

The existing `node --test` suites stay.

### 6.8 Cloud sessions and Projects: the widget fallback

Mod hooks run in cloud sessions, but panes, bands and toasts do not draw there. The owner
uses Projects (beta) cloud threads and needs the same flow there. Spike result, 2026-10-04: a
widget posted into a project thread called `sendPrompt("bt approve spike-0001 9f2c")` on a
button press. The text landed in the owner's message box, and arrived in the thread as the
owner's own message once they pressed Enter. A widget can fill the message, never send it, so
every widget action is two steps: press the button, then press Enter. Each widget says so next
to its buttons.

**Three display modes, picked at run time by the skills:**

| Mode | When | What the user gets |
| --- | --- | --- |
| Mod | The mod's pane can draw (terminal, Desktop) | Section 6.1 to 6.5 |
| Widget | The session has a tool that posts interactive widgets (Projects threads) | The same cases view, approval card and terms editor as posted widgets |
| Chat | Neither (Codex, plain cloud sessions, `claude -p`) | Text summaries and typed commands |

**Widget content.** `bt.py widget cases|approval <hash>|terms <case>|savings` prints a
self-contained HTML fragment built from shipped templates under
`skills/betterterms-guardrails/assets/widgets/`. The agent posts that output as is. The terms
widget never prefills the walk-away, because the agent would have to read it to do so. It
shows "set" or "not set" and an empty field.

**Widget buttons send typed commands as the user.** The grammar, one command per message:

```
bt approve <case_id> <hash8>
bt reject <case_id> <hash8>
bt floor <case_id> <amount>
bt terms <case_id> target=<amount> alternative=<amount>
```

The same commands typed by hand work in every Claude Code session. Codex has no prompt hook
in this release, so Codex users set the walk-away with the terminal command and approve in chat.

**A `UserPromptSubmit` settings hook in the plugin** (`hooks/prompt_commands.py`) reads each
prompt before the model does. It looks only at the user's own text: in a Projects thread, the
body of the triggering `from="human"` message, never text the agent or a counterparty wrote.

- `bt floor`: writes the walk-away through `bt.py case set-floor` on stdin, then blocks the
  prompt, so the model never receives it. The message stays visible in the thread to project
  members, and Claude Code still writes blocked prompts to the session log
  (anthropics/claude-code#96891). A `PreToolUse` hook denies agent reads of the session log
  and of `.floor` files. That guard is best effort.
- `bt approve`: records an approval for that exact rendered-text hash in
  `<case>/held/<hash>.approved`, then lets the prompt through with a note that the draft is
  approved, so the agent resends. The gate accepts `--approved` only when that file exists and
  the hash matches the newly rendered text, and it deletes the file after one use.
- `bt reject` and `bt terms`: write the change and let the prompt through with a note.

**Strength, stated plainly in the docs.** Widget approval is weaker than a mod keypress. The
agent can write files, so the `PreToolUse` hook denying writes under `held/` is the only guard
against a forged approval. It does stop the main threat: text inside an inbound email can never
become a user message, so it can never approve a draft. This matches chat approval in Codex.

**Tests.** Unit tests feed the hook real prompt shapes: a plain prompt, a Projects wake
envelope with one human message, an envelope where an agent message contains `bt approve`
(ignored), a malformed amount (exit 2 with a plain error), and a hash that does not match
(no approval written). The dogfood case (section 1, item 4) runs once locally with the mod
and once in a Projects cloud thread with widgets.

## 7. Decision records to write

- 0012 Cockpit mod and approvals by key or click (amends 0007: walk-away may also be set and
  shown in the pane, entry still never passes through the agent).
- 0013 Removed hosts and features (jurisdiction rules, claude.ai zips, Gemini, Cursor, Muse).
- 0014 config.yaml.
- 0015 Deferred metrics and pack evals.
- 0016 Quoting a counterparty's price (section 4.4).
- 0017 Display modes and the widget fallback for cloud sessions (section 6.8).

## 8. Build and release order

1. Removals (section 2), so later lanes do not touch dead files.
2. Core fixes and config.yaml (sections 3, 4, 5).
3. Mod (sections 6.1 to 6.7), then the widget fallback and prompt hooks (section 6.8).
4. Docs, version 0.10.0, CHANGELOG.
5. Full verify, dev eval, holdout through a separate agent, install tests, dogfood case.
6. `/ship`, then `/land-and-deploy`, then make the repo public. Kill the keep-awake process.

Each lane is one Devin run in its own worktree, reviewed and verified before merge into
`feat/release-v1`. A lane that touches prompts or skills records the dev eval before and after.
