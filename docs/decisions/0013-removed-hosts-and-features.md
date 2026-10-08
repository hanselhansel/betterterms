# 0013. Removed hosts and features

Status: accepted (owner decision 2026-10-04). Date: 2026-10-04.

## Context

The v1 release review found hosts and features that were planned or
shipped but never install-tested: Gemini CLI (`gemini-extension.json`,
`GEMINI.md`), Cursor (`.cursor-plugin/plugin.json`), Muse
(`.muse-plugin/plugin.json`, an undocumented format the repo could
only copy by shape), the claude.ai zip upload path
(`scripts/zip-skills`), and the per-country channel rules feature
(`rules/jurisdictions/` and the `jurisdiction` config key, which the
design spec described but no code ever built). Shipping them would
put untested install paths and unverified legal-rule promises in
front of strangers.

## Decision

Remove them completely: code, manifests, generators, the
`gemini-validate` verify check, tests, and user-facing doc mentions
(README, install guide, skill and pack text). The supported hosts
are Claude Code (plugin and mod), Codex (plugin), and any agent that
reads a vendored `skills/` tree. The Agent Plugins root `plugin.json`
stays for other readers.

Rights files keep their sourced consumer and employment rules; the
word "jurisdiction" and the by-place rules framing leave the shipped
files, replaced by "state or country" and "where the user lives or
works" wording, because no shipped file may promise per-country
call or recording rules. The `jurisdiction` config key and
`rules/jurisdictions/` directory leave the design spec. Dated
records (CHANGELOG, decisions, plans, research, older spec text)
keep their mentions.

## Consequences

`tests/test_removals.py` scans tracked files for the removed names
and fails if any return outside the dated records. Generated
commands were rebuilt; `scripts/build` no longer knows the three
host generators. If a host is re-adopted later, its manifest is a
new generator with install evidence, not a revival of these files.
