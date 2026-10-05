# TODOS

## Dev tooling (scripts/)

Deferred from the step 1 ship (owner approved 2026-10-03), to fix first in step 2.

## Gate word lists (deferred from the step 2 ship, owner approved 2026-10-04)

- **Priority:** P3. Free-text period words after a placeholder ({offer}/month, {offer} per month) with a once-period offer pass; the period should come from the structured period field (best-effort word lists, 0010 amendment).

## Mod send check (deferred, decision 0020)

- **Priority:** P1. Mod send check: send through a betterterms-owned send tool instead of inspecting arbitrary connector calls.

## Walk-away and approval guard (deferred, decision 0019)

- **Priority:** P1. Design a walk-away and approval guard that does not parse shell (for example an OS-level separate user or keychain for the floor). The `PreToolUse` file guard shipped in step 4 was removed for 0.10.0: it blocked first-case writes, research source adds and unrelated projects, and it was bypassable because the hook and the agent run as the same OS user.

## Gate probing (accepted limit, pre-landing review decision D)

- **Priority:** P1. The gate has no probe counter: an agent could binary-search the floor through repeated `gate` calls until a block flips to pass. Standing mitigations are the skills' per-turn gate-call cap and the redraft-once rule; add a per-case probe counter in bt.py that escalates after N floor-related verdicts in a window. (btlib/gate.py)
- **Priority:** P1. `bt.py score` reads the same `.floor` the gate does, so repeated score calls can be probed the same way; the per-case probe counter above must cover score calls too. (btlib/score.py)

## Accepted limits (pre-landing review)

- **Priority:** P1. Shared Projects threads are single-trust: any member's `bt approve` or `bt floor` counts as the user. Scope approvals and floor writes to the case owner (for example a member allowlist) before sensitive cases run in shared threads. (hooks/prompt_commands.py)
- **Priority:** P2. The approval hash binds the send tuple only, not the recipient; an approved text sent to a different counterparty still spends the marker. Fold the channel or recipient into the tuple when sends carry one. (btlib/held.py)
- **Priority:** P2. `case set-floor` and the typed `bt floor` parse a comma as a thousands separator, so a decimal comma (`62,50`) reads as 6250; document the dot or accept locale forms. (btlib/cli_extra.py)

## Completed

- **Priority:** P2. `scripts/vendor-into-repo` enables the plugin unpinned, so a vendored repo tracks whatever the marketplace serves; pin or hash the installed build. **Completed:** feat/lane-cloud, vendoring no longer enables a plugin at all; the copied skills and hooks are pinned to the checkout they came from.
- **Priority:** P2. Tokens with apostrophe suffixes ("deal's", "dollar's", "USD's", "k's") bypass whole-token word lists; strip possessive and contraction suffixes before matching. (skills/betterterms-guardrails/scripts/btlib/review.py) **Completed:** release v1
- **Priority:** P2. Scale words missing: lakh, crore, quadrillion, mn, mln, bln, tn, bil. (btlib/wordlists.py) **Completed:** release v1
- **Priority:** P2. Currency words missing: franc, pence, penny, rupiah, ruble, dinar, sterling, plurals of listed singulars, RMB, BTC. (btlib/wordlists.py) **Completed:** release v1
- **Priority:** P2. Commitment word forms missing: agrees, charged, cancelling, cancellation, paid, paying, deals, "sign us up", "count us in". (btlib/wordlists.py) **Completed:** release v1
- **Priority:** P3. "dozen" and ordinals (fifth, ninth, twelfth, twentieth) are not number words. (btlib/wordlists.py) **Completed:** release v1
- **Priority:** P3. Very large plan.yaml (2,600 facts) takes about 1.5 s CPU to parse; cap input file size before parsing. (btlib/cases.py, bt.py) **Completed:** release v1
- **Priority:** P2. bump-version rollback: refuse non-regular-file targets before writing; attempt every restore, list failures, re-raise the original error. (scripts/bump-version:92-96) **Completed:** step 2
- **Priority:** P2. build: refuse any path segment equal to `.git` (case-insensitive), not only the first. (scripts/build:38) **Completed:** step 2
- **Priority:** P2. build: reject generated paths that change under normalization; dedupe on the normalized, lower-cased form. (scripts/build:66) **Completed:** step 2
- **Priority:** P3. checks_scan.display(): decode with backslashreplace so non-ASCII names do not crash. (scripts/_lib/checks_scan.py:222) **Completed:** step 2
- **Priority:** P3. build: generators may not write VERSION or kit.config.json. **Completed:** step 2
- **Priority:** P3. prose-rules: inflected banned words (crucially, robustness). (scripts/_lib/checks_prose.py:18-22) **Completed:** step 2
- **Priority:** P3. no-local-paths: catch home paths in parentheses and quotes; lookahead (?![\w.-]). (scripts/_lib/checks_files.py:37) **Completed:** step 2
- **Priority:** P3. skill-names: use fullmatch so a trailing newline fails. (scripts/_lib/checks_skills.py:11,72) **Completed:** step 2
- **Priority:** P3. Scan decoded frontmatter strings for banned words and local paths (escaped \u sequences). (checks_prose.py:52, checks_files.py:84) **Completed:** step 2
- **Priority:** P3. no-symlinks vs evals/holdout: drop the symlink suggestion from the plan and evals README; .gitignore entries without trailing slash; apply _skipped to the full path. **Completed:** step 2
- **Priority:** P3. Tests for the symlink guards in checks_prose._data_files and check_skill_names. **Completed:** step 2
- **Priority:** P3. checks_files.py module docstring lists the symlink check. **Completed:** step 2
- **Priority:** P4. verify ROOT pointing at another repo runs its tests (document or restrict); bump-version accepts same or lower version silently. **Completed:** step 2
