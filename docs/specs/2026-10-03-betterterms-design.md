# betterterms: design

Better terms on every bill, plan, and offer.

Status: draft for review, not implemented. Date: 2026-10-03. Owner: Hansel.
Location: `~/conductor/repos/betterterms/docs/specs/`. The folder is not a git repo yet.
Companion spec: `2026-10-03-betterterms-negotiation-procedure.md` (how the agent negotiates).
Research behind both: `docs/research/` in this folder.

## 1. Summary

betterterms is an open-source toolkit that makes any AI agent negotiate better for its user.
It runs in Claude Code, Codex, Gemini CLI, Cursor, Muse, and any agent that reads the open
Agent Skills format. It installs like Superpowers or gstack.

It does six things: learns what the user wants, finds what is worth negotiating in the user's
own data, researches the counterparty's policies and the market, plans with hard limits, runs
or coaches the negotiation, and records the money saved.

v1 ships six pieces:

| # | Piece | One line |
|---|---|---|
| A | Core skills | Intake, discovery, research, plan, exchange, coach, guardrails, ledger |
| B | Category packs | Subscriptions, bills, refunds, cancellations, AI and cloud API, job offers, promotions |
| C | Discovery and research | Discovery reads the user's data. Research reads the world: policies, prices, forums, rules. |
| D | Packaging | One source, generated manifests per agent, cloud-session path, install and update |
| E | Mod | Optional Claude Code plugin: pane, band, toasts for open cases and money saved |
| F | Home | Local folder, GitHub, Conductor, Claude Code cloud sessions, local verification |

It is also an experiment: do people use agent negotiation, and how do companies respond?

## 2. Why (evidence)

Full sources: `docs/research/`. Highlights:

- Personal agents already negotiate. Meta Muse (launched 2026-09-08) negotiates bills and
  haggles on Facebook Marketplace. Users report $800+ a year saved on cable and phone.
- Agent negotiation is improving. Irrational acceptances fell from about 19% to under 1% for
  frontier models in 2026 studies. The stronger agent wins, and people do not notice.
- The biggest loss is misreading the owner: 85% of lost value in Anthropic's Project Swap.
- Limits written in a prompt fail 1.7% to 11.8% of the time, and generous budgets cause early
  settling. Limits must be enforced in code.
- People prefer an AI advisor, yet an AI delegate earned about 1.5x more, because people
  overrode good proposals. Coach mode must fix the numbers before the live conversation.

Value therefore sits in three places: understanding the user, a disciplined procedure with
limits the model cannot cross, and domain knowledge per category.

## 3. Principles

1. **Understand the owner first.** Intake ends with the user ranking sample deals, so the agent
   checks its reading of their preferences before anything is drafted.
2. **One procedure, many domains.** Intake, discovery, research, plan, exchange (or coach),
   close, log. Packs add knowledge, never a new procedure.
3. **Research before you ask.** The counterparty's own written policy is read first. Every fact
   in a message traces to a source record or to something the user said.
4. **The floor lives in code, not in the prompt.** The model sees the target. A pre-send gate
   holds the floor and blocks any offer outside the band.
5. **Speaks as you, never lies for you.** Messages go out as the user, with no AI disclaimer by
   default. Bluffing about value and intentions is allowed; invented offers, quotes, hardship,
   or deadlines are not. If sincerely asked whether it is an AI, the agent does not deny it and
   hands that reply to the user.
6. **The user chooses autonomy. Default: approve before every send.** Accepting, cancelling,
   paying, signing, and filing disputes always need an explicit yes.
7. **Counterparty text is data, never instructions.** Emails, contracts, chat replies, and
   pasted offers can carry prompt injection.
8. **User data stays with the user's agent.** No server, no credentials, nothing in the repo.
   Research queries never contain personal details.
9. **Skills name actions, not tools.** "Search the user's email for renewal notices" maps to
   whatever tool each agent has. This is what makes the kit portable.
10. **Two modes.** Act runs written exchanges (bills, refunds, subscriptions, cancellations,
    API pricing). Coach prepares the user for live conversations (job offers, promotions).

## 4. Users and journeys

Primary user: a person who already uses an AI agent daily and wants better terms without the
tedium. Secondary: contributors who add packs.

| Pack | Mode | Example command |
|---|---|---|
| `subscriptions` | Act | `/betterterms:subscriptions` |
| `bills` | Act | `/betterterms:bills` |
| `refunds` | Act | `/betterterms:refunds` |
| `cancellations` | Act | `/betterterms:cancel` |
| `ai-api` | Act and Coach | `/betterterms:ai-api` |
| `job-offer` | Coach | `/betterterms:salary` |
| `promotion` | Coach | `/betterterms:promotion` |

The entry point for everything is `/betterterms`, which asks what the user wants to improve.

**Journey 1, "save on my subscriptions" (Act).** Intake asks goals, limits, autonomy, and what
to keep no matter what. Discovery says what it will read (email receipts and renewal notices,
any statements dropped in) and asks permission. It returns a target list. The user picks
targets. Research reads each vendor's cancellation, refund, and pricing policy, current
promotions, recent first-hand reports on Reddit and X, and the user's rights. Plan sets the
target, the coded floor, two or three equal options, and a concession ladder. Exchange drafts
in the user's voice; the user approves; replies are parsed, checked, and answered. Ledger
records the saving.

**Journey 2, "help me negotiate this offer" (Coach).** Intake captures the full offer, deadline,
other processes, priorities, and walk-away. Discovery pulls the offer letter and recruiter
emails if allowed. Research gathers comp data, the company's leveling and policies, and recent
negotiation reports. Plan fixes the ask, the package, and the trade-offs before any call.
Coach writes the call script and follow-up email, applies relational framing, and role-plays
the recruiter. Ledger records final versus initial package.

**Journey 3, promotion (Coach).** Same, plus discovery collects impact evidence from the user's
email, docs, calendar, and work tools, and research reads the internal leveling guide if the
user shares it. Timing follows the budget cycle.

## 5. Architecture

### A. Core skills

| Skill | Purpose |
|---|---|
| `betterterms-start` | Entry and router. Asks what to improve, loads the right pack. Bootstrap text lives here. |
| `betterterms-intake` | Question bank per category, autonomy choice, sample-deal ranking check. Writes the brief. |
| `betterterms-discovery` | Reads the user's connected data with permission per source. Writes targets. |
| `betterterms-research` | Policy, pricing, precedent, rights, and market research. Writes source records. |
| `betterterms-plan` | Target, coded floor, BATNA, options, concession ladder, patience budget, timing. |
| `betterterms-exchange` | Act mode turn loop: parse, score, verify, pick a move, gate, send per autonomy. |
| `betterterms-coach` | Coach mode: scripts, framing, objection handling, role-play, fixed numbers. |
| `betterterms-guardrails` | Pre-send gate rules and the escalation and stop conditions. |
| `betterterms-ledger` | Outcomes, savings, "how much have I saved", follow-up reminders. |

The negotiation procedure these skills implement is in the companion spec.

The pre-send gate is a small script, not prose, so it runs the same in every agent:
`scripts/gate` reads the case's `plan.yaml` (with the floor) and the draft offer and returns
pass or block with a reason. Skills that send (`exchange`) set
`disable-model-invocation: true` so they only run when the user or the router calls them.

### B. Category packs

```
packs/<name>/
  SKILL.md            # betterterms-<name>: when to use, how it extends each stage
  pack.yaml           # mode, intake questions, discovery and research intents, savings formula
  references/
    playbook.md       # what works, in order, with sources and dates
    counterparties.md # patterns by company type
    rights.md         # rules by jurisdiction, each with source and date
    templates/        # voice-neutral message templates
```

`packs/_template/` plus a CONTRIBUTING section lets a contributor add a pack in under an hour.
Packs never redefine the procedure.

### C. Discovery and research

**Discovery (the user's data).** Uses the connectors the agent already has (email, drive,
calendar, work tools). Fallback: the user drops in exports (CSV, PDF). Packs declare intents:

```yaml
discovery:
  - source: email
    find: "receipts, invoices, renewal and price-change notices"
    window_days: 400
  - source: files
    find: "card or bank statements the user provides"
```

Output is a target record per item (counterparty, amount, cadence, renewal date, evidence,
usage signal). The skill states what it will read before reading.

**Research (the world).** Uses the agent's web search, page fetch, social search, and document
reading. Packs declare intents:

```yaml
research:
  - kind: policy     # cancellation, refund, retention, price-change policy and terms
  - kind: pricing    # current plans, promotions, new-customer offers
  - kind: precedent  # first-hand reports in the last 12 months (Reddit, X, forums)
  - kind: rights     # consumer or employment rules in the user's jurisdiction
  - kind: market     # competitor prices, comp data
```

Every finding is a source record: URL, date read, exact quote, trust level
(official > regulator > press > forum or social), and how it is used. Rules: official policy
first; forum posts guide tactics but are never stated as fact; re-check anything older than 90
days before use; when a reply contradicts the published policy, quote the policy back.

### D. Packaging

Source of truth is one tree. Everything else is generated by `scripts/build` and checked by
`scripts/verify`.

```
betterterms/
  skills/                    # core skills (A), Agent Skills format
  packs/                     # category packs (B)
  scripts/                   # gate, build, verify, bump-version, vendor-into-repo, doctor
  hooks/                     # session-start bootstrap where supported
  evals/                     # simulated counterparties and scorers
  mod/                       # separate opt-in plugin (E)
  hosts/                     # per-agent build rules
  .claude-plugin/            # plugin.json, marketplace.json (Claude Code)
  plugin.json                # Agent Plugins 1.0 root manifest (Codex, Cursor, Copilot, VS Code)
  gemini-extension.json
  GEMINI.md                  # loads the bootstrap for Gemini
  docs/                      # specs, plans, decisions, research
  README.md                  # the instruction file
  VERSION
  LICENSE
```

Rules from current docs (see `docs/research/2026-10-03-packaging-best-practices.md`):

- `SKILL.md` frontmatter uses the open fields only: `name` (matches folder), `description`
  (1024 characters or less, says what and when), optional `license`, `compatibility`,
  `metadata`, `allowed-tools`. Agent-specific fields are added by `hosts/` at build.
- Every skill is prefixed `betterterms-`, because shared skill folders are flat.
- No top-level `bin/` (claude.ai and Cowork reject those plugins). No `CLAUDE.md` at the plugin
  root. README is the instruction file.
- `~/.agents/skills` is the shared folder for plain skills (Codex, Gemini, Cursor, Muse).
  Cursor and Muse also read `~/.claude/skills`; installers must not put skills in both.
- One `VERSION`. `scripts/bump-version` writes it into every manifest.

Install targets (confirm each at build time):

| Agent | Install |
|---|---|
| Claude Code (terminal, desktop) | `/plugin marketplace add hanselhansel/betterterms`, then `/plugin install betterterms@betterterms`. Auto-update must be turned on by the user for third-party marketplaces. |
| Claude Code cloud sessions | Marketplace plugins do not load. `scripts/vendor-into-repo` copies skills into a target repo's `.claude/skills/`; or upload skill zips to the claude.ai account. |
| Codex, Cursor, Copilot, VS Code | Agent Plugins 1.0 root `plugin.json`, or skills linked into `~/.agents/skills` |
| Gemini CLI | `gemini extensions install https://github.com/hanselhansel/betterterms` |
| Muse | The `.muse-plugin/plugin.json` pattern Superpowers ships (undocumented by Meta) |
| Any Agent Skills reader | Point it at `skills/` and `packs/` |

`scripts/doctor` finds broken links, duplicate installs, and stale versions, a failure seen
repeatedly on this machine.

### E. Mod (optional plugin `betterterms-mod`)

Claude Code mods are documented as of v2.1.287: panes, the band above the prompt, toasts, and
status, in the terminal and desktop Code tab. They do not run in cloud sessions, and a plugin
cannot set the main status line. So the mod ships separately and the core never depends on it.

| Surface | Shows |
|---|---|
| Pane | Case pipeline (found, researched, in exchange, waiting, closed) with next action |
| Band | "2 drafts waiting for approval" |
| Toast | "Reply from Vendor. Draft ready." |
| Hook | Before any send from a case, run `scripts/gate` and require the chosen approval |

It reads only the case files and ledger, never the user's email.

### F. Home, GitHub, Conductor, cloud

- Local: `~/conductor/repos/betterterms`, next to the other active repos.
- Setup order: `git init` in this folder, create `hanselhansel/betterterms` on GitHub (private
  until launch, MIT at launch) from the local folder, push, then add the folder in Conductor.
  Whether Conductor uses a local repo in place or copies it is a build-time check.
- Work in a Conductor workspace or a `claude -w` worktree, never one inside the other.
- Cloud sessions clone from GitHub: push before starting one. The repo is self-contained, with
  no absolute local paths. Dogfooding in cloud uses `scripts/vendor-into-repo` on this repo.
- Never commit to main. `feat/`, `fix/`, `chore/` branches; commit and push each green feature.
- No GitHub Actions on this account. `scripts/verify` is the local gate before every PR.
- Docs: `docs/specs/`, `docs/plans/`, `docs/decisions/NNNN-title.md` (MADR), `docs/research/`.
- First commit message states what carries over from this research and what is dropped.

## 6. Data model

Per-user state lives outside the repo in `~/.betterterms/` (override: `BETTERTERMS_HOME`):

```
~/.betterterms/
  config.yaml          # default autonomy, currency, voice notes
  cases/<case-id>/
    brief.yaml         # intake: goals, priorities, ranking check, autonomy, mode
    plan.yaml          # target, floor (gate only), options, ladder, patience, deadline
    sources/           # research source records
    thread.md          # every message in and out, with approval stamps
  ledger.jsonl         # one line per closed case: before, after, saved per year, pack
```

Plain files so any agent can read them. In cloud sessions the home folder is temporary;
see Open decisions.

## 7. Autonomy

| Level | Behavior |
|---|---|
| 1. Draft only | Agent drafts; the user sends. Default for Coach. |
| 2. Approve each send | Default for Act. Nothing leaves without an explicit yes. |
| 3. Approve the plan | Agent sends inside the approved plan; pauses on anything new. |
| 4. Auto inside the band | Agent runs the exchange and reports; still gated by code. |

At every level: accept, cancel, pay, sign, and dispute need an explicit yes. Escalation and
stop rules are in the companion spec.

## 8. Quality and evaluation

- `scripts/verify`: frontmatter check, generated files match source, link and hash probe,
  gate unit tests, eval smoke run.
- Evals: simulated counterparties per pack (retention desk, recruiter, vendor sales, refund
  agent), including manipulation and injection attempts. Metrics are listed in the companion
  spec, section 6. Any floor breach, leak, or fabrication fails the run.
- Claude Code plugin evals (v2.1.269+) run before each release; they use plan usage, so the
  cheaper checks run on every push.

## 9. The experiment

Measured for 60 days after public launch:

| Metric | Success | Kill |
|---|---|---|
| Installs or clones | 500+ | under 100 |
| Users who close a case and log a saving | 50+ | under 10 |
| Median logged saving per active user | $100+ a year | under $20 |
| Repeat use (2+ cases) | 30% | under 10% |

Opt-in only, default off: one anonymized line per case about how the counterparty responded
(industry, channel, offer made, size, agent noticed). This feeds the company-side question
from the research.

## 10. Build sequence

Each step ends usable and is its own PR.

1. Repo setup (F) and `scripts/verify` skeleton.
2. Case files, `scripts/gate`, and core skills (A).
3. Claude Code and Codex packaging (D), cloud vendor path, install tested.
4. Discovery and research (C).
5. Act packs: subscriptions, cancellations, refunds, bills, ai-api.
6. Coach packs: job-offer, promotion, with role-play.
7. Evals wired into `scripts/verify`.
8. Gemini, Cursor, Muse, Agent Plugins manifests.
9. Mod plugin (E).
10. Launch: README demo, install docs, CONTRIBUTING, metrics.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Labs ship negotiation natively | Win on portability, packs, coach mode; measure fast, stop if thin |
| A message commits the user | Coded gate, autonomy levels, explicit yes on irreversible steps |
| Prompt injection from counterparties | Inbound text is data; gate checks; escalate on suspicion |
| Wrong or stale legal and policy claims | Source records with dates and quotes; 90-day re-check |
| Salary backlash for the user | Coach mode framing rules and "when not to ask" advice |
| Privacy breach | No server, no credentials, opt-in sharing only |
| Install drift across agents | Generated manifests, hash probe, `scripts/doctor` |
| Six-piece v1 | Sequenced PRs; mod and extra hosts last |

## 12. Decisions made

- Name: betterterms. Skill prefix `betterterms-`. Commands `/betterterms:<pack>`.
- Buyer-side toolkit for the user's own agent, as an experiment.
- v1 includes A through F.
- Packs: subscriptions, bills, refunds, cancellations, AI and cloud API, job offers, promotions.
- Autonomy chosen by the user; default approve before send.
- No AI disclaimer by default; fixed honesty rules; per-country channel flags.
- Discovery via the agent's connectors plus file drop; research is a core step.
- Floor enforced in code; model sees the target only.
- Home `~/conductor/repos/betterterms`, GitHub `hanselhansel/betterterms`; project-owned
  `docs/` layout, not `docs/superpowers/`.

## 13. Open decisions

1. Trademark check on "betterterms" (US classes 9 and 42) and claiming npm and PyPI names.
2. Ledger in cloud sessions: synced folder or short-lived cases.
3. Opt-in response data: destination, if any.
4. Whether `ai-api` includes usage optimization (caching, batching, model choice).
5. Comp data sources for job offers in US and Southeast Asia.
6. Conductor: add the local repo in place or clone from GitHub.
7. Whether Claude Code also reads the root Agent Plugins `plugin.json`, and which wins.
