# Changelog

## [0.10.0] - 2026-10-04

### Added
- `~/.betterterms/config.yaml` (`autonomy`, `currency`, `sign_off`,
  `voice_notes`, mode 0600) read by `case new` to prefill new cases;
  `bt.py config show` and `bt.py config set <key> <value>`.
- Held drafts: a `needs_approval` verdict writes `held/<hash>.yaml` in
  the case folder, so drafts survive restarts and are rebuilt into the
  Approvals tab. Approvals bind to the SHA-256 of the send tuple
  (action, offer, period, currency, rendered text) as
  `held/<hash>.approved`, are written only by a user action, and are
  consumed atomically after one send. Held records whose stored fields
  do not hash back to their filename never list.
- `bt.py held disarm <case_id> <hash8>` removes only the `.approved`
  marker and keeps the held draft; `betterterms-mod` runs it when a
  marker it re-armed was not spent by the re-gate. In mod mode an
  approval lives in `$.state` only, recorded by the pane press or the
  mod's `prompt.submit` hook on a typed `bt approve`; a `.approved`
  file on disk never authorizes a send by itself.
- Typed commands through a `UserPromptSubmit` hook
  (`hooks/prompt_commands.py`): `bt approve`, `bt reject`, `bt floor`,
  `bt terms` with `target=` and `alternative=` keys in either order.
  `bt floor` writes on stdin and blocks the prompt so the model never
  receives the walk-away; malformed or embedded lookalikes block too.
  In a cloud session the session-start hook warns when the betterterms
  home sits in the ephemeral VM home.
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
  scans case folders on stat fingerprints with burst reuse, and its
  send guard applies one strict shape: exactly one argument equals the
  freshly re-gated rendered text, other string leaves are
  whitespace-free tokens under any key name (addresses, channel,
  message and thread ids) or a subject/title of at most 80 characters
  with no digits, numeric leaves deny, and a Bash call is never a send.
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
- `scripts/vendor-into-repo` enables the plugin without copying the
  skills (a copy would load each skill twice); `--no-plugin` vendors
  the skills alone.
- `scripts/doctor` reports native Windows as unsupported.

### Removed
- Gemini, Cursor and Muse manifests and generators, claude.ai skill
  zips (`scripts/zip-skills`), and per-country jurisdiction rules; the
  hosts were never install-tested and the rules were never verified
  (decision 0013). Supported hosts: Claude Code (plugin and mod),
  Codex (plugin), and agents that read a vendored `skills/` tree.
- The optional anonymized response-sharing line; no such code ships.

### Deferred
- The always-on `PreToolUse` file guard (decision 0019): removed after
  review showed it blocking first-case writes, research source adds
  and files in unrelated projects, while staying bypassable because
  the hook and the agent run as the same OS user. Docs state the
  same-user limit plainly; an OS-level guard design is a P1 TODO.
- The 12 negotiation metrics, multi-turn simulated counterparties,
  and the 14 pack eval cases; evals stay at 12 cases (decision 0015).

## [0.1.0] - 2026-10-03

### Added
- Design spec, negotiation procedure spec, research notes, the v1 implementation plan, and decision records 0001 to 0005.
- `python3 scripts/verify`, one local command that runs the unit tests and every repo check: skill names and frontmatter, no `bin/`, no `CLAUDE.md`/`AGENTS.md`, no local paths, no symlinks, prose rules (no em dashes, banned words), file size, vendored-code sync, generated-file freshness and version sync. Claude and Gemini plugin validation run when those CLIs are installed.
- `scripts/build` and `scripts/bump-version`, the generator registry and version tool that later steps use to write each host's manifests from one `VERSION`.
- A YAML layer built on bundled pure-Python PyYAML 6.0.3, so the toolkit needs no installs. It rejects duplicate keys, aliases and merge keys and reports errors with line numbers.

### Changed
- The YAML layer replaced an earlier hand-written parser that disagreed with real YAML on edge cases.
- `scripts/build` never deletes files and refuses unsafe write paths.
