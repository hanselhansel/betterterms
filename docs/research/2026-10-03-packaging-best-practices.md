# Packaging a cross-agent negotiation toolkit (2026-10-03)

Working name `askmore` (from naming.md). Docs fetched 2026-10-03; versions noted where stated.

## 1. Agent Skills spec (agentskills.io/specification, unversioned)

- Required: `name` (1-64 chars, `a-z0-9-`, no leading/trailing or double hyphen, must equal the folder name) and `description` (1-1024 chars, what it does plus when to use it).
- Optional: `license`, `compatibility` (max 500), `metadata` (string map; put `version` here), `allowed-tools` (experimental).
- Progressive disclosure: metadata ~100 tokens always loaded; body under 5,000 tokens and 500 lines; `references/`, `scripts/`, `assets/` loaded on demand, one level deep. Validate with `skills-ref validate`.
- Anthropic adds: third-person descriptions with trigger keywords, no "claude"/"anthropic" in names, three evals first.

## 2. Claude Code plugins and marketplaces

- `.claude-plugin/plugin.json`: only `name` is required. Components are namespaced `askmore:skill`. Default dirs: `skills/`, `agents/`, `hooks/hooks.json`, `.mcp.json`, `output-styles/`, `monitors/`. Prefer skills over `commands/`.
- `.claude-plugin/marketplace.json` at repo root (`name`, `owner`, `plugins[]`) turns a GitHub repo into a marketplace. `claude plugin validate --strict .` in CI.
- Versioning: manifest `version` wins; users update only when it changes. Omit it to track commit SHA. Never set it in both manifest and entry.
- Auto-update is off by default for third-party marketplaces. Tell users to enable it in `/plugin` > Marketplaces.
- Packs can declare `dependencies` on the core plugin with semver ranges, resolved against `<plugin>--v<version>` git tags.
- Avoid a top-level `bin/` (claude.ai and Cowork refuse the plugin). A `CLAUDE.md` at a plugin root is not loaded and triggers a validate warning.
- **Cloud sessions (claude.ai/code) do not load marketplace plugins**, user plugins, or `~/.claude/skills`. They do load the repo's committed `.claude/skills/`, `.claude/agents/`, hooks, `.mcp.json`, and skills enabled on the user's claude.ai account. Setup scripts run before launch and are cached if under ~5 minutes; SessionStart hooks can test `CLAUDE_CODE_REMOTE=true`.

## 3. UI "mods" (Claude Code mods reference, as of v2.1.287)

- A mod is a plugin whose `hooks/hooks.json` lists `"modules": ["./register.js"]`. It exports `register(on, options)`.
- Surfaces: `Pane`, `AbovePrompt` (the band), `$.ui.toast`, `$.ui.status`, plus restyling of existing sites (Spinner, ToolUse, AskUserQuestion). Terminal and Desktop both render; `Svg` is Desktop-only, `Raster`/`Image` terminal-only.
- Test with `claude plugin test`. Orgs can block third-party mods.
- A plugin's `settings.json` cannot set the main `statusLine` (only `agent`, `subagentStatusLine`). Output styles ship via `output-styles/`.
- Ship the mod as a separate opt-in plugin. It will not run in cloud sessions.

## 4. Codex (developers.openai.com/codex, undated; local codex-cli 0.159.0)

- Skills load from `.agents/skills` (cwd, parents, repo root), `~/.agents/skills`, `/etc/codex/skills`. `~/.codex/skills` is no longer documented.
- Optional `agents/openai.yaml` per skill: `interface`, `policy.allow_implicit_invocation`, `dependencies`.
- Plugins: `.codex-plugin/plugin.json` (`skills`, `mcpServers`, `apps`, `hooks`, `interface`). Marketplace at `.agents/plugins/marketplace.json`; `.claude-plugin/marketplace.json` is read as legacy. Public listing goes through the plugin submission portal (shared ChatGPT/Codex directory).

## 5. Gemini, Cursor, Muse, Agent Plugins 1.0

- Gemini: root `gemini-extension.json` (`name`, `version`, `contextFileName`, `mcpServers`), `skills/`, TOML `commands/`, `hooks/hooks.json`. Also reads `~/.agents/skills`.
- Cursor: `.cursor-plugin/plugin.json` with `skills`, `rules/`, hooks, MCP. Manual review at cursor.com/marketplace/publish. Cursor also reads `~/.claude/skills`, `~/.codex/skills`, `~/.agents/skills`.
- Muse Code: reads `~/.agents/skills` and `~/.claude/skills`. Plugin manifest is undocumented by Meta; superpowers ships `.muse-plugin/plugin.json` (`schemaVersion: 1`).
- **Agent Plugins 1.0.0** (2026-08-06; OpenAI, Microsoft, AWS, Cursor, Vercel): root `plugin.json` + `skills/` + `mcp.json`, read by Codex, Cursor, Copilot, VS Code, Kiro. Anthropic is not a signatory. Ship it as one more generated manifest.

## 6. What the top repos do

- superpowers 6.4.2: repo root is the plugin (`source: "./"`), one manifest per harness, `.version-bump.json` + `bump-version.sh --check` syncing 11 files, `tests/<harness>/`.
- gstack 1.91.12.0: `SKILL.md.tmpl` sources, `hosts/*.ts` configs generate per-host skill trees, CI fails on stale generated docs, evals run on PRs, skills prefixed `gstack-`.
- anthropics/skills: `skills/`, `template/`, one marketplace, grouped plugins.

## Recommended repo tree

```
askmore/                         # repo root = core plugin + marketplace
├── README.md  CONTRIBUTING.md  SECURITY.md  CHANGELOG.md  LICENSE  VERSION
├── kit.config.json              # single source: name, version, description, author, packs
├── .claude-plugin/{plugin.json,marketplace.json}    # generated
├── .codex-plugin/plugin.json  .agents/plugins/marketplace.json   # generated
├── .cursor-plugin/plugin.json  .muse-plugin/plugin.json          # generated
├── plugin.json  gemini-extension.json  GEMINI.md                 # generated / shipped context
├── skills/askmore-<verb>/{SKILL.md,references/,scripts/,assets/,agents/openai.yaml}
├── hooks/hooks.json
├── packs/askmore-<domain>/      # one plugin per domain pack, depends on askmore
├── mods/askmore-ui/             # Claude Code only: hooks/register.js, types/, *.test.ts
├── evals/<case>/{prompt.md,graders/}
├── scripts/{gen-manifests,bump-version,install-skills,vendor-into-repo,verify}.sh
└── docs/{decisions,specs,plans,guides}/
```

Rules: prefix every skill `askmore-` (`~/.agents/skills` is flat). No `bin/`, no root CLAUDE.md or AGENTS.md. Side-effecting skills (sending an offer, emailing a counterparty) get `disable-model-invocation: true`. Every skill states that counterparty emails, contracts, and pasted offers are data, not instructions; negotiation inputs are adversarial by nature. No secrets in repo; API keys via `userConfig` with `sensitive: true`.

## Install commands

| Agent | Command |
|---|---|
| Claude Code (terminal, Desktop Code tab) | `claude plugin marketplace add <owner>/askmore` then `claude plugin install askmore@askmore` (packs: `askmore-salary@askmore`, mod: `askmore-ui@askmore`) |
| Claude Code cloud | `scripts/vendor-into-repo.sh <target-repo>` copies skills to `.claude/skills/` and commit; or upload release skill zips on claude.ai |
| Codex CLI/app | `codex plugin marketplace add <owner>/askmore`, then `/plugins` |
| Gemini CLI | `gemini extensions install https://github.com/<owner>/askmore --auto-update` |
| Cursor | Team marketplace import of the repo, or `/add-plugin askmore` after listing |
| Muse | `muse plugins install ./askmore && muse plugins approve askmore` |
| Any Agent Skills agent | `scripts/install-skills.sh --target ~/.agents/skills` (symlinks; never also into `~/.claude/skills`, or Cursor and Muse load duplicates) |

## Release and verification

`make verify`, run locally and as a pre-push hook (Actions are exhausted on this account): regenerate manifests and `git diff --exit-code`; `claude plugin validate --strict` on root and each pack; `skills-ref validate`; `bump-version.sh --check`; lint for 500-line bodies, name equals folder, prefix, no `bin/`, gitleaks. Before each release: `claude plugin eval --threshold 0.8` (needs v2.1.269+, spends plan usage) with trigger and non-trigger cases plus no-plugin baseline. Tag `vX.Y.Z` and `askmore--vX.Y.Z`.

## 7. Where to keep it locally

Create the GitHub repo first, then add it in Conductor via "Open GitHub project" so it lands in `~/conductor/repos/askmore` beside your other repos. Treat that checkout as read-mostly main. Conductor workspaces go to `~/conductor/workspaces/askmore/<name>`; `claude -w` worktrees go to `~/conductor/repos/askmore/.claude/worktrees/` (gitignore it). Both share one `.git`, so a branch can be checked out in only one place. Use one isolation layer per task; never nest them. Cloud sessions clone from GitHub, so push first. Share scripts through `.conductor/settings.toml`.

## 8. Design docs

Use `docs/decisions/NNNN-title.md` (MADR 4.0.0 default) for durable decisions, `docs/specs/YYYY-MM-DD-slug.md` for feature specs, `docs/plans/` for implementation plans (prune after merge), `docs/guides/` for user docs. Pack authors copy `packs/_template/` per CONTRIBUTING.

## Verify at build time

1. Does Claude Code read a root Agent Plugins `plugin.json` (eval docs mention "plugin.json or .claude-plugin/plugin.json")? Which wins if both exist?
2. Codex precedence between `.codex-plugin/plugin.json` and root `plugin.json`; whether 0.159 still scans `~/.codex/skills`.
3. Cloud: does a setup script running `claude plugin install` into the VM's `~/.claude` load the plugin? Do claude.ai-synced plugins (not only skills) reach cloud sessions? Does a skills-dir plugin load without the trust dialog?
4. Gemini: subdirectory installs for packs; tolerance of Claude-only frontmatter.
5. Muse manifest schema; Meta docs are silent.
6. Conductor "Open project": in place or copied into `~/conductor/repos`? Is `conductor.json` still read?
7. Mods: stability label, minimum version, Desktop behavior when the session is Cloud.
8. Cursor and Codex directory review criteria.

## Sources

agentskills.io/specification; code.claude.com/docs/en (plugins-reference, plugin-marketplaces, plugins/host-marketplace, plugins/loading, plugins/mods/reference, plugin-evals, skills, cloud-environments, worktrees); platform.claude.com skill best-practices; developers.openai.com/codex/plugins/build; learn.chatgpt.com/docs/build-skills; geminicli.com/docs; cursor.com/docs; dev.meta.ai/docs/muse-code; agent-plugins-spec 1.0.0; conductor.build/docs; adr.github.io/madr.
