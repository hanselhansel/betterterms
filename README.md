# betterterms

betterterms is an open-source toolkit that teaches your AI agent to negotiate
for you. It learns what you want, finds the bills and offers worth
negotiating in your own data, reads the counterparty's policies and the
market, plans with a walk-away limit held in code, then runs the written
exchange or coaches you for the live call. It runs in Claude Code, Codex,
and any agent that reads the open Agent Skills format.

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

macOS, Linux, or WSL. `bt.py` uses Unix file locking, so native
Windows is unsupported (`scripts/doctor` reports it).

| Host | Install |
|---|---|
| Claude Code (terminal, desktop) | `/plugin marketplace add hanselhansel/betterterms`, then `/plugin install betterterms@betterterms`. Auto-update for third-party marketplaces is off until you enable it. |
| Claude Code cloud sessions | Run `python3 scripts/vendor-into-repo <repo>`: it enables the plugin through `<repo>/.claude/settings.json`, so the session installs it (skills, typed commands) from `github.com/hanselhansel/betterterms`, which must be reachable from the session (public works). `--no-plugin` vendors the skills alone for sessions that cannot reach the marketplace. Cases kept in the cloud home vanish when the VM ends; export what you want to keep. |
| Codex | `codex plugin marketplace add hanselhansel/betterterms`, then `codex plugin add betterterms@betterterms`. Codex has no slash commands: name the skill instead (`betterterms-start` routes, `betterterms-subscriptions` starts a pack). |
| Other Agent Plugins readers | The repo root carries an Agent Plugins 1.0 `plugin.json` pointing at `skills/`; add the repo as a plugin source in your host. |
| Any Agent Skills reader | `python3 scripts/install-skills --target ~/.agents/skills`. |

Per-host detail, updating, and uninstall: [docs/guides/install.md](docs/guides/install.md).

## Quickstart

**Lower a subscription (Act).** Run `/betterterms:subscriptions`. Answer the
intake questions, then set your walk-away number yourself: the skill prints
an absolute `bt.py case set-floor` command for your terminal (hidden
prompt), or you type `bt floor <case_id> <amount>` as a chat message the
prompt hook intercepts before the model sees it. Discovery asks permission
before reading receipts and renewal mail, then returns a target list. Pick
targets; each pick is its own case. The agent researches each vendor's
policies and current promotions, builds a plan, and drafts messages in your
voice. Drafts the gate holds wait as files; you approve the exact rendered
text by keypress in the mod's Approvals tab or a typed `bt approve`, and
the hash of that text binds the approval to one `gate --approved` run. The
ledger records what you saved.

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

- You type your walk-away number in your own terminal. It lands in a
  `.floor` file the gate and the scorer read; the skills instruct the
  model never to read it, and the chat never repeats it.
- Every message passes a coded pre-send gate. Offers worse than your number
  block. Irreversible actions need your explicit yes.
- Message text that looks risky (money typed outside the price placeholders,
  agreement wording, unusual characters) comes back to you for approval
  instead of sending.
- Drafts carry no typed prices. Money reaches a message only through
  placeholders the gate renders itself.

The gate is a safety net, not a sandbox. The default autonomy asks before
every send. One honest limit: the agent runs as your user, so nothing
technical stops it from reading the walk-away file or writing an approval
marker if it tries (decision 0019). The skills instruct it never to,
the gate blocks any draft that states the walk-away, and of the typed
`bt` commands only `bt floor` is kept from the model where the prompt
hook runs; `bt approve`, `bt reject` and `bt terms` are handled first,
then passed through with a note. Approvals in every mode are enforced by
the gate's hash-bound one-use `--approved` marker: a pane press in the
mod or a `bt approve` you type writes it. Full detail:
[docs/guides/safety-model.md](docs/guides/safety-model.md).

## Privacy

There is no server and no account. Case files, the ledger, and your settings
live in `~/.betterterms` on your machine. Skills read your connected data
only after asking, per source. Research queries never contain personal
details.

## The optional mod

`betterterms-mod` is a separate Claude Code plugin in the same marketplace
(`/plugin install betterterms-mod@betterterms`). It adds a cockpit pane
(Cases, Approvals, Savings tabs), a terms editor, a band over the prompt
counting held drafts, one-line gate rows, and toasts on new counterparty
replies. It reads only your case files and ledger, and never inspects
outgoing tool calls or prompts: approving a held draft writes the
hash-bound marker and tells the agent to run `bt.py gate --approved`
once. The core kit never depends on it.

Where the mod cannot draw, the same surfaces come through two fallbacks:
in sessions that can post interactive widgets (Projects cloud threads)
the skills post `bt.py widget` HTML whose buttons type `bt` commands into
your message box, and everywhere else you get plain text plus the same
typed commands. Full detail and what each mode guarantees:
[docs/guides/quickstart.md](docs/guides/quickstart.md).

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
