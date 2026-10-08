# Changelog

## [0.10.1] - 2026-10-08

### Changed
- The README now illustrates the bill, proposed offer, and draft approval flow with the approved Betterterms cover and descriptive alt text.

## [0.10.0] - 2026-10-08

### Added
- `~/.betterterms/config.yaml` (`autonomy`, `currency`, `sign_off`,
  `voice_notes`, mode 0600) read by `case new` to prefill new cases;
  `bt.py config show` and `bt.py config set <key> <value>`.
- Held drafts: a `needs_approval` verdict writes `held/<hash>.yaml` in
  the case folder, so drafts survive restarts and are rebuilt into the
  Approvals tab. Approvals bind to the SHA-256 of the send tuple
  (action, offer, period, currency, rendered text) plus a digest of
  the inbound message the user reviewed, as `held/<hash>.approved`,
  are written only by a user action, and are consumed atomically
  after one send. A changed or newly flagged inbound needs a fresh
  approval, even for identical text. Held records whose stored
  fields do not hash back to their filename never list.
- `bt.py held drop <case_id> <hash8>` removes the record and marker
  with no thread marker; the mod runs it when an edited draft replaces
  the held one. An approval pressed in the pane or typed through
  `bt approve` applies only while the hash is the case's current
  `gate.json` hash: a stale hash is refused plainly.
- Typed commands through a `UserPromptSubmit` hook
  (`hooks/prompt_commands.py`): `bt approve`, `bt reject`, `bt floor`,
  `bt terms` with `target=` and `alternative=` keys in either order.
  `bt floor` writes on stdin and blocks the prompt so the model never
  receives the walk-away; `bt approve`, `bt reject` and `bt terms`
  are handled first, then passed through with a note. `bt floor`
  lookalikes block anywhere in the raw prompt the moment a digit
  follows: the floor rule runs over the whole message as a
  fail-closed backstop, inside wake-envelope text included.
  `bt approve`, `bt reject` and `bt terms` lookalikes block only
  when the message starts with them (one leading backtick or a
  leading slash allowed) and still carry the piece the verb needs:
  a hex token of six or more characters for approve and reject, `=`
  for terms. Anything else is prose and passes untouched. A prompt
  counts as a wake envelope only when it starts with `<wake` and
  carries a `<message>` element; a trailing or mid-text `<wake` tag
  is plain user text.
  The session-start hook prints the marker "betterterms: typed bt
  commands are active in this session." only after the prompt check
  runs successfully; otherwise it says typed commands are off and
  held drafts stay held. The skills offer typed `bt` commands and
  widgets only when they see the marker. The start pointer
  and, in a cloud session, the warning that the betterterms home sits
  in the ephemeral VM home print only when a case exists.
- `betterterms-mod`, an optional Claude Code cockpit plugin: pane with
  Cases, Approvals and Savings tabs, band above the prompt, gate rows,
  toasts, and a terms editor that sets the walk-away by drag, nudge or
  a typed field through `case set-floor` on stdin.
- `bt.py widget cases|approval|terms|savings`: self-contained HTML
  fragments for hosts that post interactive widgets (Projects cloud
  threads). Buttons fill the user's message box with a typed `bt`
  command; Enter sends it.
- One case per counterparty: discovery hands each picked target to its
  own `case new`, each with its own walk-away.
- `bt.py where` reports the runtime's absolute path; user-facing
  commands print it instead of relative paths.

### Changed
- The gate renders `{quote:n}` from the inbound `amounts` list: quoted
  counterparty text and numbers never count as offers and never meet
  the worse-than-floor check, while a rendered value equal to the
  walk-away still blocks. `never_disclose` entries with letters block
  on appearance; explicit `period: null` is an input error; a blocked
  draft never reports "offer is at your limit"; ledger reads a nested
  line without recursion errors, appends a leading newline when the
  file lacks one, and holds a lock across read and append.
- `scripts/verify` runs the mod suites with `node --test` inside
  `mod/`, and runs `claude plugin validate --strict mod` and
  `claude plugin test mod` through a pseudo-terminal when stdout is
  not a TTY; both report `SKIP` when the `claude` binary is absent.
- Root `plugin.json` gains the `skills` key. Docs describe the three
  display modes (mod, widget, chat) and what each guarantees.
- The mod finds the core `bt.py` through the marketplace cache layout,
  scans case folders on stat fingerprints with burst reuse, never
  caches a case whose held list could not run, revalidates a cached
  `bt.py` path, and scans case folders in parallel. Editing a held
  draft in the pane drops the old record quietly before the re-gate,
  and an approval for a hash that is not the case's current
  `gate.json` hash refuses as stale.
- `bt.py ledger add` accepts `--period once` for one-time savings,
  recorded as `saved_once` and totaled in `once_by_currency` /
  `once_by_pack`, never folded into the per-year figures; widgets,
  the mod status line and the Savings tab show them as "$N once".
  `ledger total` groups records without a currency under `unknown`.
  `case new` validates `config.yaml` before touching the case tree.
- `gate.json` is written on every `bt.py gate` call, blocked input
  included, so the case folder always holds the last verdict.
- Held records written by builds before tuple-bound names (the
  filename hashed the rendered text alone) still list, flagged
  `legacy: true` with the note "held by an older version; re-run the
  gate". They cannot be approved or spent: re-run the gate on each
  case's `draft.yaml` to hold it under the current hash. The mod
  never counts them.
- The prompt hook treats `bt` as a command only at a token boundary
  (`debt terms`, `doubt floor` pass through) and fails closed when
  `bt.py` does not answer inside 7 seconds, within the 10-second hook
  budget. The cloud session-start warning prints only when a case
  exists to lose.
- An approval is spent by claiming the marker with an atomic rename
  before unlinking: on filesystems where a racing `unlink` can report
  success twice, two sends still cannot share one approval. The mod's
  scan fingerprints case files by inode with mtime and size, never
  caches a case whose held list could not run, revalidates a cached
  `bt.py` path, and scans case folders in parallel.
- Autonomy 2 means approve each send in code now, not only in docs:
  the gate holds every send at levels 1 and 2 for a hash-bound
  approval; levels 3 and 4 behave as before. When a gate call holds
  a new draft for a case, the previous current held record is dropped
  quietly, like `held drop`; the cockpit lists a superseded record
  greyed and labeled, outside the band and badge counts, while it
  lasts. The Approvals tab sorts the current card first and gives it
  the `a`/`e`/`r` keys, the approve press has a one-press-per-hash
  in-flight guard and skips an already-approved record, and saving an
  edit toasts the new gate verdict.
- The approve instructions in the mod and the prompt hook print the
  whole runnable command (`python3 <resolved bt.py> gate <case_id>
  --draft <case dir>/draft.yaml [--inbound <case dir>/inbound.yaml]
  --approved`), told to run exactly once and to send the returned
  rendered text verbatim only on a `pass` verdict; a `needs_approval`
  or `block` verdict sends nothing. The mod's fallback toast on a
  failed prompt submit carries the same command.
- The prompt hook runs through `hooks/prompt-guard.sh`, which blocks
  the prompt when the check fails, times out (8 seconds at most) or
  cannot start. Scanning is linear, prompts over 256 KB block, and
  the floor rule now blocks a walk-away written in number words,
  spaced or glued, with or without a case id, without echoing it.
  The session-start marker prints only when this check works.
- Any blocked input or gate error retires outstanding consent, and
  every pass, block or new hold supersedes the previous held record
  and its approval. Floor-relative review reasons read "a value in
  this draft needs your review" instead of naming the relationship.
- Approval cards in the pane and the widget show the action, exact
  amount, currency and period being approved. Editing a held draft
  in the pane keeps the held record's action, offer and period,
  drops claims, and round-trips leading spaces and blank lines.
- Skill prose: only a typed `bt approve <case> <hash8>` or an actual
  pane or widget click approves; a "yes" in chat approves nothing.
- `scripts/vendor-into-repo` migrates an older vendored prompt hook
  to the guarded launcher and refuses, before writing, an owned hook
  that sits in a pipe.
- A `bt.py gate` transcript row collapses to the one-line verdict
  only for a plain standalone invocation; a command composed with
  `;`, `&&`, `||`, pipes, redirects, substitutions or a second line
  keeps the stock row.
- `scripts/vendor-into-repo` no longer writes `enabledPlugins` or
  `extraKnownMarketplaces`: cloud sessions never install plugins a
  repo declares. It now vendors the skills into
  `<repo>/.claude/skills/`, copies the hook scripts into
  `<repo>/.claude/betterterms/hooks/`, and merges `UserPromptSubmit`
  and `SessionStart` entries into `<repo>/.claude/settings.json`
  with `$CLAUDE_PROJECT_DIR` paths, keeping other keys and never
  duplicating entries; vendored hooks apply only in a session with
  one repository. `--no-hooks` vendors the skills alone.
- `scripts/doctor` reports native Windows as unsupported.

### Removed
- Gemini, Cursor and Muse manifests and generators, claude.ai skill
  zips (`scripts/zip-skills`), and per-country jurisdiction rules; the
  hosts were never install-tested and the rules were never verified
  (decision 0013). Supported hosts: Claude Code (plugin and mod),
  Codex (plugin), and agents that read a vendored `skills/` tree.
- The optional anonymized response-sharing line; no such code ships.

### Deferred
- The mod's outgoing `tool.call` send check (decision 0020): removed
  after four review rounds could not settle one rule that admits every
  legitimate send shape and denies every forged one. The mod ships as
  a cockpit only; approvals in every mode are enforced by the gate's
  hash-bound one-use `--approved` marker. A betterterms-owned send
  tool is the future boundary (P1 TODO).
- The always-on `PreToolUse` file guard (decision 0019): removed after
  review showed it blocking first-case writes, research source adds
  and files in unrelated projects, while staying bypassable because
  the hook and the agent run as the same OS user. Docs state the
  same-user limit plainly; an OS-level guard design is a P1 TODO.
- The 12 negotiation metrics, multi-turn simulated counterparties,
  and the 14 pack eval cases; evals stay at 12 cases (decision 0015).

### Known limits
- Shared Projects threads are single-trust: any member can approve a
  draft or set the walk-away.
- `bt.py score` can be probed for the floor like the gate can.
- `scripts/vendor-into-repo` vendored hooks apply only in a
  single-repository cloud session; multi-repo Projects threads
  ignore them.
- Approvals bind the send tuple, not the recipient.
- A decimal comma in an amount parses as a thousands separator.
- Released with known open review findings (release under owner
  override, see PR #2):
  - An approval stays usable after the walk-away, terms, never-disclose
    list or autonomy change.
  - A `{quote:n}` placeholder can render a quoted amount above the
    walk-away and pass the gate at autonomy 3 or 4.
  - The floor rule misses walk-aways written with non-ASCII digits or
    full-width or other Unicode letters.
  - The prompt guard's timeout kill needs `ps`; without it a hung
    check is not killed.
  - Vendor migration does not refuse an owned hook chained with `;`,
    a newline, `&` or `|&`, or a short host timeout.
  - `scripts/install-skills --copy --target` pointed at the repo's own
    `skills/` folder deletes the source skills. Do not run it that way.
  - Control or bidirectional characters in a held draft display raw on
    the approval card.

## [0.1.0] - 2026-10-03

### Added
- Design spec, negotiation procedure spec, research notes, the v1 implementation plan, and decision records 0001 to 0005.
- `python3 scripts/verify`, one local command that runs the unit tests and every repo check: skill names and frontmatter, no `bin/`, no `CLAUDE.md`/`AGENTS.md`, no local paths, no symlinks, prose rules (no em dashes, banned words), file size, vendored-code sync, generated-file freshness and version sync. Claude and Gemini plugin validation run when those CLIs are installed.
- `scripts/build` and `scripts/bump-version`, the generator registry and version tool that later steps use to write each host's manifests from one `VERSION`.
- A YAML layer built on bundled pure-Python PyYAML 6.0.3, so the toolkit needs no installs. It rejects duplicate keys, aliases and merge keys and reports errors with line numbers.

### Changed
- The YAML layer replaced an earlier hand-written parser that disagreed with real YAML on edge cases.
- `scripts/build` never deletes files and refuses unsafe write paths.
