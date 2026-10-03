# betterterms

betterterms is an open-source toolkit that teaches your AI agent to negotiate
for you. It learns what you want, finds the bills and offers worth
negotiating in your own data, reads the counterparty's policies and the
market, plans with a walk-away limit held in code, then runs the written
exchange or coaches you for the live call. It runs in Claude Code, Codex,
Gemini CLI, Cursor, and any agent that reads the open Agent Skills format.

It is for people who already use an agent daily and want better terms without
the tedium. It is also for contributors who add packs for new categories.

## The seven packs

| Pack | Command | Mode | What it covers |
|---|---|---|---|
| subscriptions | `/betterterms:subscriptions` | Act | recurring plans, memberships |
| cancellations | `/betterterms:cancel` | Act | getting out, or staying for less |
| refunds | `/betterterms:refunds` | Act | money back from merchants |
| bills | `/betterterms:bills` | Act | broadband, mobile, insurance |
| ai-api | `/betterterms:ai-api` | Act and Coach | AI and cloud API pricing |
| job-offer | `/betterterms:salary` | Coach | job offers and comp packages |
| promotion | `/betterterms:promotion` | Coach | raises and promotions |

`/betterterms` alone asks what you want to improve and routes you to the
right pack.

Act means the agent runs the written exchange: support emails, retention
desks, billing threads. Coach means it prepares you for a conversation you
hold yourself: fixed numbers, a script, and a rehearsal before the call.

## Install

| Host | Install |
|---|---|
| Claude Code (terminal, desktop) | `/plugin marketplace add hanselhansel/betterterms`, then `/plugin install betterterms@betterterms`. Auto-update for third-party marketplaces is off until you enable it. |
| Claude Code cloud sessions | Marketplace plugins do not load there. Run `python3 scripts/vendor-into-repo <repo>` to copy the skills into a repo's `.claude/skills/`, or run `python3 scripts/zip-skills` and upload the zips from `dist/` to your claude.ai account. |
| Codex | `codex plugin marketplace add hanselhansel/betterterms`, then `codex plugin add betterterms@betterterms`. |
| Gemini CLI | `gemini extensions install https://github.com/hanselhansel/betterterms`. |
| Cursor, Copilot, VS Code | The repo root carries an Agent Plugins 1.0 `plugin.json` pointing at `skills/`; add the repo as a plugin source in your host. |
| Any Agent Skills reader | `python3 scripts/install-skills --target ~/.agents/skills`. |
| Muse | A `.muse-plugin/plugin.json` manifest ships in the repo, provided untested: the format is undocumented. |

Per-host detail, updating, and uninstall: [docs/guides/install.md](docs/guides/install.md).

## Quickstart

**Lower a subscription (Act).** Run `/betterterms:subscriptions`. Answer the
intake questions, then set your walk-away number in your own terminal when
the skill prints the `bt.py case set-floor` command; the prompt hides what
you type. Discovery asks permission before reading receipts and renewal mail,
then returns a target list. Pick targets; the agent researches each vendor's
policies and current promotions, builds a plan, and drafts messages in your
voice. You approve each send. The ledger records what you saved.

**Negotiate a job offer (Coach).** Run `/betterterms:salary`. Share the offer,
the deadline, and your priorities, and set your walk-away number the same
way. The agent gathers comp data, fixes your ask and package before the call,
writes your script, and plays the recruiter in rehearsal. You hold the live
conversation, then debrief and send the drafted follow-up.

Step by step: [docs/guides/quickstart.md](docs/guides/quickstart.md).

## Autonomy

| Level | Behavior |
|---|---|
| 1. Draft only | The agent drafts; you send. Default for Coach. |
| 2. Approve each send | Default for Act. Nothing leaves without your explicit yes. |
| 3. Approve the plan | The agent sends inside the approved plan and pauses on anything new. |
| 4. Auto inside the band | The agent runs the exchange and reports. The gate still applies. |

At every level, accept, cancel, pay, sign, and dispute always need your
explicit yes.

## Safety model

- You type your walk-away number in your own terminal. It lands in a file
  only the gate and the scorer read; the model never sees it and the chat
  never repeats it.
- Every message passes a coded pre-send gate. Offers worse than your number
  block. Irreversible actions need your explicit yes.
- Message text that looks risky (money typed outside the price placeholders,
  agreement wording, unusual characters) comes back to you for approval
  instead of sending.
- Drafts carry no typed prices. Money reaches a message only through
  placeholders the gate renders itself.

The gate is a safety net, not a sandbox. The default autonomy asks before
every send. Full detail: [docs/guides/safety-model.md](docs/guides/safety-model.md).

## Privacy

There is no server and no account. Case files, the ledger, and your settings
live in `~/.betterterms` on your machine. Skills read your connected data
only after asking, per source. Research queries never contain personal
details. Optional anonymized response sharing is off.

## The optional mod

`betterterms-mod` is a separate Claude Code plugin in the same marketplace
(`/plugin install betterterms-mod@betterterms`). It adds a case-pipeline
pane, a band counting drafts waiting for approval, and toasts on new
counterparty replies. It reads only your case files and ledger. The core kit
never depends on it.

## Troubleshooting

`python3 scripts/doctor` checks `~/.agents/skills` and `~/.claude/skills` for
broken links, duplicate installs, and stale versions, and prints one line per
finding.

## Development

Run the full local verify before every PR. It runs the unit tests and every
repo check:

```bash
python3 scripts/verify
```

To add a pack in under an hour, see [CONTRIBUTING.md](CONTRIBUTING.md).
Design and procedure specs live in `docs/specs/`; decision records live in
`docs/decisions/`.

## License

MIT. See [LICENSE](LICENSE).
