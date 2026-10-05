# betterterms v1 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship betterterms 0.10.0 from `feat/release-v1`: removals, gate and CLI fixes, config.yaml,
the cockpit mod, the cloud widget fallback, then verify, evals, install tests, dogfood, ship, land
and make the repo public.

CURRENT_WORKING_FILE: docs/plans/2026-10-04-betterterms-v1-release.md

**Architecture:** All business rules stay in `bt.py` and `btlib/` (Python 3, stdlib plus vendored
PyYAML). The mod (`mod/`, the opt-in `betterterms-mod` plugin) and the new settings hooks
(`hooks/`, core plugin) call `bt.py` through a subprocess and parse its JSON. Approval is bound to
the SHA-256 of the rendered text and recorded only by a user action: a mod keypress or click, or a
`bt approve` message caught by the `UserPromptSubmit` hook.

**Tech Stack:** Python 3.9+, vendored PyYAML, Node 20 `node --test`, Claude Code mods v2.1.287
(`claude plugin validate`, `claude plugin test`), promptfoo evals.

**Spec:** `docs/specs/2026-10-04-betterterms-v1-release-design.md`

**Execution:** each task below is one Devin lane: a worktree off `feat/release-v1` named
`lane-r<N>`, run with `devin --model swe-2-max --permission-mode dangerous -p --prompt-file <brief>`.
The orchestrator writes the brief from this task, reviews the diff, runs the full
`python3 scripts/verify`, and merges into `feat/release-v1`. Tasks R2 and R3 change prompts or
skills, so the orchestrator records `scripts/eval --dev` before and after them.

## Global Constraints

- Every source file stays under 400 lines. `btlib/gate.py` is at 399, so any gate change first
  moves code out of it.
- Prose in shipped files: no em dashes; none of delve, pivotal, crucial, showcase, leverage
  (verb), robust, comprehensive, nuanced, underscore, foster, moreover, furthermore. `verify`'s
  `prose-rules` check enforces this.
- No home-directory paths in shipped files (`no-local-paths`). No `CLAUDE.md` or `AGENTS.md` in
  the repo.
- `bt.py` exit codes: 0 ok or pass, 1 block, 2 usage or input error, 3 needs approval. Every
  command prints one JSON object.
- The walk-away never appears in argv, in `bt.py` stdout, or in any text the agent reads. It
  enters only through `bt.py case set-floor` on stdin.
- The gate never reads `config.yaml`.
- Approvals bind to the full SHA-256 hex of the rendered text. Commands accept the first 8 hex
  characters (`hash8`) and fail with exit 2 when they match zero or more than one held draft.
- Command grammar (spec 6.8), one per message, case-insensitive verb, case ids as `bt.py` prints
  them:
  `bt approve <case_id> <hash8>` · `bt reject <case_id> <hash8>` · `bt floor <case_id> <amount>` ·
  `bt terms <case_id> target=<amount> alternative=<amount>`
- Amounts accept `62`, `62.50`, `$62`, `1,200`. Anything else is exit 2 with a plain message.
- Mod limits: hook work under 10 s, no waiting on own promises inside hooks, no arrow-key
  bindings, SVG only on `desktop`, `Raster` only on `terminal`. Amended by decision 0020: the
  mod registers no `tool.call` or `prompt.submit` hook; it is a cockpit only.
- Supported hosts after R1: Claude Code (plugin, mod), Codex (plugin), vendored `skills/`.

## Review Focus

1. A Projects wake envelope that quotes an earlier agent message containing `bt approve`: only
   the triggering `from="human"` body counts, so nothing is approved (test in R4).
2. Two held drafts in one case whose hashes share the first 8 characters: approve exits 2 and
   names both, never approves the wrong one (test in R3).
3. The user edits a held draft and then approves the old card from a stale widget: the hash no
   longer matches, so the send is denied again (test in R3 and R5).
4. Claude Code restarts with drafts held: the Approvals tab and `bt.py held list` show them
   from files, and an approval file from the old session still works only for the same text
   (test in R3 and R5).
5. A terminal narrower than 144 columns: the pane does not open by itself, but the band and the
   status line still show held drafts (test in R5).

---

### Task R1: Remove jurisdiction rules, claude.ai zips, Gemini, Cursor and Muse

**Files:**
- Delete: `GEMINI.md`, `gemini-extension.json`, `scripts/zip-skills`, `scripts/_lib/gen_gemini.py`,
  `scripts/_lib/gen_cursor.py`, `scripts/_lib/gen_muse.py`
- Modify: `scripts/build` (drop the three generators from `GENERATORS`), `scripts/verify` and
  `scripts/_lib/checks_tools.py` (drop `check_gemini_validate`), `scripts/install-skills`,
  `scripts/doctor`, `docs/guides/install.md`, `README.md`, `CHANGELOG.md` (leave history lines),
  `docs/specs/2026-10-03-betterterms-design.md` (`jurisdiction` key and `rules/jurisdictions/`),
  pack `references/rights.md` and `templates/pack/references/rights.md` lines that promise
  per-country call or recording rules
- Modify tests: `tests/test_build_hosts.py`, `tests/test_install.py`, `tests/test_verify_tools.py`
- Create: `docs/decisions/0013-removed-hosts-and-features.md`

- [ ] **Step 1: Write the failing test** `tests/test_removals.py::test_removed_hosts_absent`:
  assert none of the deleted paths exist, and `grep -ril` over tracked files (excluding
  `CHANGELOG.md` and `docs/decisions/`) finds no match for `gemini`, `cursor rules`,
  `\.cursor/`, `muse`, `zip-skills`, `jurisdiction`.
- [ ] **Step 2:** `python3 -m pytest tests/test_removals.py -v` fails.
- [ ] **Step 3:** delete and edit the files listed. Decision 0013 lists what was removed and why
  (owner, 2026-10-04).
- [ ] **Step 4:** `python3 -m pytest tests -q` and `python3 scripts/verify` pass.
- [ ] **Step 5:** commit `chore: remove jurisdiction rules, zips, and untested hosts`.

### Task R2: Gate fixes, template self-check, quoting rule

**Files:**
- Create: `skills/betterterms-guardrails/scripts/btlib/quotes.py` (quote rendering and the
  quote-amount rule moved out of `gate.py`)
- Modify: `btlib/gate.py`, `btlib/review.py`, `btlib/cases.py`, `btlib/ledger.py`,
  `btlib/wordlists.py` (template phrases), shipped templates under `skills/*/references/templates/`
  where a phrase trips review
- Create: `scripts/_lib/checks_templates.py` with `check_templates_gate(root) -> (bool, str)`,
  registered in `scripts/verify` as `templates-gate`
- Test: `tests/test_quotes.py`, `tests/test_templates_gate.py`, `tests/test_step2_findings.py`
- Create: `docs/decisions/0016-quoting-counterparty-price.md`

**Interfaces:**
- Produces: `quotes.quote_amounts(rendered_spans) -> list[Decimal]` is no longer fed to the
  floor check; `gate.check(case_dir, draft, approved=False, inbound=None)` keeps its signature
  and return `(result, reasons, rendered)`.

- [ ] **Step 1: Write the failing tests**
  - `test_quote_above_floor_passes_floor_check`: pay-direction case, floor 60, inbound amounts
    `[89]`, draft template `"You charged {quote:1}. Please cancel."`, action `cancel`: result is
    not `block`, and no reason mentions the limit.
  - `test_offer_above_floor_still_blocks`: same case, `offer: 89`, template `"I can pay {offer}."`:
    result `block`.
  - `test_quote_checked_against_never_disclose`: `never_disclose: ["CHF 90"]`, inbound text
    contains `CHF 90`, template quotes it: result `block`.
  - `test_never_disclose_with_letters_blocks`: items `"CHF 90"` and `"$85/month"` appearing in
    free text block.
  - `test_period_null_is_input_error`: an option with `period: null` makes `bt.py gate` exit 2.
  - `test_block_never_says_at_limit`: a blocked draft's reasons never contain `at your limit`.
  - `test_ledger_nested_line_no_recursion`, `test_ledger_append_adds_missing_newline`,
    `test_ledger_concurrent_adds_count_once` (two processes add the same case; total counts it
    once).
  - `test_templates_gate_passes_all_shipped`: `check_templates_gate(REPO)` returns `True`; and a
    fixture template containing `no longer works for me` passes review at autonomy 3 and 4.
- [ ] **Step 2:** run them, all fail or error.
- [ ] **Step 3:** implement. Quote rule per spec 4.4: amounts rendered from `{quote:n}` are
  quotes, never offers. Fix `works for me` matching so a longer phrase that negates it does not
  match. The template check renders each `references/templates/*.md` code block with the
  fixture case `tests/fixtures/template_case/` and runs the gate at autonomy 3 and 4; any
  `needs_approval` or `block` fails with the template path. Close each confirmed step 2
  finding; for one already fixed, keep the test and note it in the commit.
- [ ] **Step 4:** `python3 -m pytest tests -q`, `python3 scripts/verify` pass; `wc -l` shows
  `gate.py` under 400.
- [ ] **Step 5:** commit `fix: quote rule, step 2 findings, and template self-check`.

### Task R3: CLI: where, config, terms, held drafts, approvals

**Files:**
- Create: `btlib/config.py`, `btlib/held.py`, `btlib/cli_extra.py` (the new subcommands, so
  `bt.py` stays small)
- Modify: `bt.py` (register subcommands), `btlib/gate.py` (hold on `needs_approval`, consume on
  `--approved`), `btlib/cases.py` (`best_alternative` in `plan.yaml`, config prefill in
  `create_case`)
- Test: `tests/test_config.py`, `tests/test_held.py`, `tests/test_cli_extra.py`
- Create: `docs/decisions/0014-config-yaml.md`

**Interfaces:**
- Produces:
  - `config.DEFAULTS = {"autonomy": 2, "currency": "USD", "sign_off": "", "voice_notes": ""}`
  - `config.load() -> dict` (missing file returns defaults; unknown key warns on stderr; bad
    value raises `BtError` naming the key)
  - `config.set_value(key: str, raw: str) -> dict` (writes `~/.betterterms/config.yaml`, 0600)
  - `held.draft_hash(rendered: str) -> str` (64 hex)
  - `held.hold(case_dir, rendered: str, reasons: list[str]) -> str` writes
    `held/<hash>.yaml` `{hash, rendered, reasons, held_at}`, returns hash
  - `held.list_held(case_dir) -> list[dict]` oldest first
  - `held.resolve(case_dir, hash8: str) -> str` full hash or `BtError`
  - `held.approve(case_dir, hash8) -> str` writes `held/<hash>.approved`
  - `held.reject(case_dir, hash8) -> str` removes the held file, records `rejected` in `thread.md`
  - `held.consume_approval(case_dir, rendered: str) -> bool` true once per approval, deletes it
  - CLI: `bt.py where` → `{"bt": "<absolute path>"}`; `bt.py config show|set <key> <value>`;
    `bt.py case set-terms <id> [--target N] [--alternative N] [--period P] [--note T]`;
    `bt.py held list <id>`; `bt.py held approve <id> <hash8>`; `bt.py held reject <id> <hash8>`
  - `bt.py gate` JSON gains `"hash"` when the result is `needs_approval`.

- [ ] **Step 1: Write the failing tests**
  - `test_config_defaults_when_missing`, `test_config_bad_autonomy_names_key` (`autonomy: 7` →
    error text contains `autonomy`), `test_config_file_mode_0600`,
    `test_new_case_prefills_from_config` (autonomy 3, currency EUR copied), `test_gate_ignores_config`
    (changing config after a pass leaves the gate result unchanged).
  - `test_needs_approval_holds_draft`: gate returns 3, JSON has `hash`, `held/<hash>.yaml` exists.
  - `test_approved_requires_matching_approval`: `--approved` without an approval file returns
    `needs_approval` with reason `no approval recorded for this exact text`; after
    `held approve` it passes once, and a second `--approved` run returns `needs_approval`.
  - `test_edited_text_invalidates_approval` (Review Focus 3).
  - `test_hash8_ambiguous_exits_2` (Review Focus 2): two fixtures with crafted hashes sharing a
    prefix; exit 2 and both full hashes in the error.
  - `test_held_survive_restart` (Review Focus 4): held files listed by a fresh process.
  - `test_where_prints_absolute_path`, `test_set_terms_writes_plan` (`best_alternative:
    {amount: 60, period: month, note: ...}`), `test_set_terms_never_touches_floor`.
- [ ] **Step 2:** run, all fail.
- [ ] **Step 3:** implement per the interfaces. Hold files are 0600, the `held/` dir 0700.
- [ ] **Step 4:** `python3 -m pytest tests -q` and `python3 scripts/verify` pass.
- [ ] **Step 5:** commit `feat: config, terms, held drafts and hash-bound approvals`.

### Task R4: Settings hooks for typed commands and the read guard

**Files:**
- Create: `hooks/prompt_commands.py`, `hooks/guard.py`, `hooks/_btpath.py` (finds `bt.py` from
  `CLAUDE_PLUGIN_ROOT`)
- Modify: `hooks/hooks.json` (add `UserPromptSubmit` → `prompt_commands.py`, `PreToolUse` with
  matcher `*` → `guard.py`)
- Test: `tests/test_prompt_commands.py`, `tests/test_guard_hook.py`

**Interfaces:**
- Consumes: R3 CLI (`case set-floor`, `held approve`, `held reject`, `case set-terms`).
- Produces: `prompt_commands.user_text(prompt: str) -> str`;
  `prompt_commands.parse(text: str) -> dict | None` (`{"verb", "case_id", ...}`);
  hook stdout per Claude Code hooks: block → `{"decision": "block", "reason": ...}`; pass with
  note → `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ...}}`.
  `guard.py` returns `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny", "permissionDecisionReason": ...}}` when any string in
  `tool_input` names a `.floor` file, a `held/` path, `held approve`, `case set-floor`, or the
  session transcript directory (`transcript_path`'s parent from the hook input).

- [ ] **Step 1: Write the failing tests**
  - `test_plain_prompt_floor_blocked_and_saved`: prompt `bt floor case-1 62` → decision block,
    floor file holds 62, stdout never contains `62`.
  - `test_wake_envelope_uses_human_trigger_only` (Review Focus 1): envelope with an agent
    message `bt approve case-1 abcd1234` and a human trigger `thanks` → no approval file, exit 0,
    no output.
  - `test_wake_envelope_human_approve`: human trigger `bt approve case-1 <hash8>` → approval
    file exists, additionalContext says the draft was approved and may be resent.
  - `test_bad_amount_message`: `bt floor case-1 sixty` → block with reason naming the format.
  - `test_unknown_case`: block with reason `no case case-9`.
  - `test_amount_formats`: `$62`, `62.50`, `1,200` parse; `62k` rejects.
  - `test_guard_denies_floor_read` (`Bash` `cat ~/.betterterms/cases/x/.floor`),
    `test_guard_denies_held_write`, `test_guard_denies_transcript_read`, `test_guard_allows_gate`
    (`bt.py gate case-1 --draft d.yaml`).
- [ ] **Step 2:** run, all fail.
- [ ] **Step 3:** implement. Wake parsing: find the `<message` element with `trigger="true"` and
  `from="human"` and take its text; unescape `&lt; &gt; &amp; &#39; &quot;`. A prompt with no
  `<wake` is used whole. Only a message whose whole trimmed text matches the grammar counts.
- [ ] **Step 4:** `python3 -m pytest tests -q`, `python3 scripts/verify` pass.
- [ ] **Step 5:** commit `feat: typed bt commands and read guard hooks`.

### Task R5: Mod cockpit: tabs, approvals, band, gate rows, status, toasts

**Files:**
- Modify: `mod/register.js` (split: keep wiring only), `mod/lib/cases.js`
- Create: `mod/lib/approvals.js`, `mod/ui/pane.js`, `mod/ui/band.js`, `mod/ui/rows.js`,
  `mod/types/index.d.ts`, `mod/approvals.test.ts` (`claude plugin test`), `mod/approvals.test.js`
  (`node --test`)
- Modify: `mod/.claude-plugin/plugin.json` (`"types": "./types/index.d.ts"`), `mod/README.md`

**Interfaces:**
- Consumes: R3 `bt.py gate` (`hash`), `held list|approve|reject`.
- Produces: `$.state` keys under `betterterms-mod`: `tab: 1|2|3`, `selected: string | null`.
  Pane id `betterterms`, command `betterterms` (keeps `betterterms-cases` as an alias).
  (Amended by decision 0020: no `approvals` state key and no `tool.call` send check; the
  Approve press runs `held approve` and submits the `gate --approved` instruction.)

- [ ] **Step 1: Write the failing tests** (each run on `terminal` and `desktop`):
  - `held draft shows band and badge`; `approve writes the marker and submits the gate prompt`
    (press `a`: `held approve` runs and the gate instruction is submitted; `gate --approved`
    spends the marker once and a second run holds again);
  - `click and key both approve` (press by key and by element);
  - `the mod registers no tool.call or prompt.submit hook`; `stale hash refused`;
  - `narrow terminal shows band without pane` (Review Focus 5: `columns: 120`);
  - `gate rows redrawn` (`ToolUse` for a `bt.py gate` call draws `✓ Gate pass`, `✗ Gate block:
    <reason>` or `● Held for you`);
  - `status line text` equals `bt: <n> cases · $<saved>/yr saved`.
- [ ] **Step 2:** `claude plugin test mod` and `node --test mod` fail.
- [ ] **Step 3:** implement per spec 6.1 to 6.3 (as amended by decision 0020). No `tool.call`
  or `prompt.submit` hook registers. Approve runs `held approve` for the card's hash8 and
  calls `$.prompt.submit` with the instruction to run `bt.py gate <case> --approved` exactly
  once and send the returned rendered text verbatim as its own argument. Edit uses an
  `Input`; saving runs `held drop`, rewrites `draft.yaml`, and runs the gate again.
- [ ] **Step 4:** `claude plugin validate --strict mod`, `claude plugin test mod`,
  `node --test mod` pass; every file under 400 lines.
- [ ] **Step 5:** commit `feat(mod): cockpit tabs and hash-bound approvals`.

### Task R6: Mod terms editor and savings charts

**Files:**
- Create: `mod/ui/terms.js`, `mod/ui/scale.js` (pure layout), `mod/client/scale-drag.jsx`
  (`Client` surface module), `mod/ui/savings.js`, `mod/scale.test.js`, `mod/terms.test.ts`

**Interfaces:**
- Consumes: R3 `case set-terms`, `case set-floor` (stdin), `ledger total`.
- Produces: `scale.fit(values: number[], full: boolean) -> {lo, hi}` (pad = max(4, 25% of
  spread), full = `[min-50%, max+50%]` rounded to 10); `scale.lanes(handles) -> handles with
  tier` (labels within 12 columns stack); `scale.warnings({target, alternative, walkaway}) ->
  string[]` with the three spec 6.4 messages.

- [ ] **Step 1: Write the failing tests**
  - `fit pads at least 4 each side`, `fit refits only on release` (drag events do not call fit),
  - `lanes stack overlapping labels`, `warnings` for each of the three conditions,
  - `save writes walk-away through stdin, never argv` (inspect the `$.process.run` call),
  - `all three fields follow a drag`, `minus and plus nudge by 1`, `z toggles full range`,
  - `savings draws Svg on desktop and Raster on terminal`.
- [ ] **Step 2:** tests fail.
- [ ] **Step 3:** implement per spec 6.4 and 6.5. Walk-away shown plainly.
- [ ] **Step 4:** `claude plugin validate --strict mod`, `claude plugin test mod`,
  `node --test mod` pass.
- [ ] **Step 5:** commit `feat(mod): terms editor and savings charts`.

### Task R7: Widget fallback for Projects threads

**Files:**
- Create: `btlib/widgets.py`, `skills/betterterms-guardrails/assets/widgets/{cases,approval,
  terms,savings}.html`, `tests/test_widgets.py`
- Modify: `bt.py`/`btlib/cli_extra.py` (`bt.py widget cases|approval <id> <hash8>|terms
  <id>|savings` → `{"html": "..."}`), `skills/betterterms-exchange/SKILL.md` and
  `skills/betterterms-intake/SKILL.md` (display mode rules, spec 6.8)

**Interfaces:**
- Consumes: R3 held and config data; R4 grammar.
- Produces: HTML fragments with no `<html>`, `<head>` or `<body>`, inline CSS with light and
  dark tokens, buttons that call `sendPrompt` with the exact grammar strings. `sendPrompt` only fills the
  user's message box, so each widget shows `Then press Enter to send.` beside its buttons.

- [ ] **Step 1: Write the failing tests**
  - `test_terms_widget_never_contains_floor` (floor 62 set; `62` absent from html),
  - `test_approval_widget_buttons` (contains `sendPrompt('bt approve <id> <hash8>')` and the
    reject string), `test_widget_escapes_text` (rendered text with `<script>` is escaped),
  - `test_widget_size_under_64k`.
- [ ] **Step 2:** fail. **Step 3:** implement; skills say: if a tool that posts interactive
  widgets is available, post the `html` from `bt.py widget`; else print text and the typed
  command. **Step 4:** tests and verify pass. **Step 5:** commit `feat: widget fallback for
  project threads`.

### Task R8: Skills, docs, decisions, version

**Files:**
- Modify: `skills/betterterms-intake/SKILL.md`, `skills/betterterms-discovery/SKILL.md` (one
  case per chosen target; commands printed with the absolute path from `bt.py where`; config
  prefill), `docs/guides/quickstart.md`, `docs/guides/install.md`, `README.md` (drop response
  sharing; hosts; mod and widget modes; Codex uses skill names), root `plugin.json` (`skills`
  key), `docs/specs/2026-10-03-betterterms-design.md` (status lines),
  `docs/research/2026-10-03-packaging-best-practices.md` (old name), `CHANGELOG.md`, `VERSION`
  via `scripts/bump-version 0.10.0`
- Create: `docs/decisions/0012-cockpit-mod-and-approvals.md`,
  `docs/decisions/0015-deferred-metrics-and-pack-evals.md`,
  `docs/decisions/0017-display-modes-and-widget-fallback.md`
- Modify: `scripts/_lib/checks_tools.py` + `scripts/verify`: `mod-tests` check runs
  `node --test mod`; `mod-validate` runs `claude plugin validate --strict mod` and
  `claude plugin test mod`, `SKIP` when `claude` is absent.

- [ ] **Step 1: failing tests** `tests/test_verify_tools.py::test_mod_checks_registered`,
  `test_mod_validate_skips_without_claude`, `tests/test_docs.py::test_no_relative_bt_paths_in_user_docs`
  (no `../betterterms-guardrails/scripts/bt.py` in `docs/guides/` or in user-facing lines of
  intake), `test_version_is_0_10_0`.
- [ ] **Step 2:** fail. **Step 3:** implement. **Step 4:** `python3 scripts/verify` all PASS.
  **Step 5:** commit `docs: release docs, decisions, and 0.10.0`.

### Task R9: Release (orchestrator, not Devin)

- [ ] Full `python3 scripts/verify` via `gstack-evidence run --label verify`.
- [ ] `scripts/eval --dev`: at least 9/12. A separate agent runs `scripts/eval --holdout` and
  returns only the pass rate: at least 10/12.
- [ ] Install tests on the final branch: Claude Code marketplace add and install (10 skills,
  mod loads), Codex marketplace add and plugin add, `scripts/vendor-into-repo`.
- [ ] Dogfood: one real case locally with the mod; one in a Projects cloud thread with widgets.
- [ ] `/ship`, then `/land-and-deploy`, then `gh repo edit --visibility public
  --accept-visibility-change-consequences`. Local `main` equals `origin/main`. Kill caffeinate.

## Order

R1 → R2 → R3 → (R4, R5, R7 in parallel) → R6 → R8 → R9. R4, R5 and R7 touch disjoint files.
