# 0011. Host manifests: Gemini, Cursor, Muse, Agent Plugins; open question 7

Status: accepted. Date: 2026-10-03.

## Context

Step 8 adds generated manifests for Gemini CLI (`gemini-extension.json`,
`GEMINI.md`), Cursor (`.cursor-plugin/plugin.json`), Muse
(`.muse-plugin/plugin.json`), and Agent Plugins 1.0.0 (root `plugin.json`).
Open question 7 in design spec section 13 asks whether Claude Code also reads
the root `plugin.json` and which manifest wins when both exist.

## Manifest shapes

- `gemini-extension.json`: `name`, `version`, `description`,
  `contextFileName: "GEMINI.md"`. `GEMINI.md` is a short bootstrap that
  includes `skills/betterterms-start/SKILL.md` via the `@./` syntax.
  `gemini extensions validate .` passes; it does not object to the
  Claude-format `commands/*.md` or `hooks/hooks.json` sitting beside it.
- `.cursor-plugin/plugin.json`: modeled on the file superpowers 6.4.2 ships
  (`skills: "./skills/"`, author, homepage, license, keywords). No `hooks`
  key: our `hooks/hooks.json` is Claude Code schema, so pointing Cursor at
  it would ship a config it cannot read.
- `.muse-plugin/plugin.json`: `schemaVersion: 1`, modeled on superpowers
  6.4.2's shipped manifest. Assumption, recorded here because Meta does not
  document the schema: `capabilities.skills` lists every skill as
  `{id, path}`; `capabilities.hooks` registers `hooks/session-start.sh`
  (plain sh, prints the betterterms-start pointer) for `SessionStart` with a
  5000 ms timeout.
- Root `plugin.json`: Agent Plugins 1.0.0. Closed schema
  (`$schema`, `name`, `version`, `description`, `author`, `homepage`,
  `repository`, `license`, `keywords`, `extensions`), `$schema` set to the
  canonical `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`.
  Skills are discovered from the fixed `skills/` location, so no `skills`
  key appears in the manifest.

## Open question 7: findings (Claude Code 2.1.288)

`claude plugin validate .` run in this repo with both
`.claude-plugin/plugin.json` and root `plugin.json` present passes.

Scratch-directory experiments on 2026-10-03:

- Valid `.claude-plugin/plugin.json` plus a root `plugin.json` holding
  invalid JSON: validate reports `Validating plugin manifest:
  .claude-plugin/plugin.json` and passes. The root file is never parsed.
- Only a root `plugin.json` (valid Agent Plugins manifest, or invalid
  JSON), no `.claude-plugin/`: validate reports `Validating components`
  and passes either way; no manifest validation runs.

Conclusion: Claude Code 2.1.288 does not read the root `plugin.json` as a
plugin manifest. `.claude-plugin/plugin.json` wins when present; the root
file is inert to Claude Code, so shipping both is safe.

## Consequences

The root `plugin.json` is written for Agent Plugins clients (Codex,
Cursor, Copilot, VS Code, Kiro) and costs nothing on Claude Code today. If
Claude Code adopts Agent Plugins later, the manifest is already correct
and `.claude-plugin/` still takes precedence by its own rules. Per the
owner decision in step 8, only Claude Code and Codex are install-tested
hosts; the other manifests are validated by shape tests and, for Gemini,
`gemini extensions validate` in `scripts/verify`.
