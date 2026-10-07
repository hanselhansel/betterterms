# betterterms evals

Simulated counterparties score the exchange skill. The agent under test
is a Claude agent (subscription, via the local Claude Code login,
provider `anthropic:claude-agent-sdk` with no tools). Grading rubrics run
on the Codex subscription (provider `openai:codex-sdk`, read-only
sandbox). The safety check is `assert_gate`, a python assertion that
runs `bt.py gate` on the draft and also fails when the floor appears in
the prose around the yaml block or in the gate's rendered text.

Layout:

- `promptfooconfig.yaml`: prompt function, agent provider, grader.
- `harness/agent_prompt.py`: builds the system prompt from the exchange
  and guardrails skills plus the output contract, and returns it via
  `config.custom_system_prompt` so it lands in the provider's real
  system slot. The user prompt carries the fixture case files (never
  the floor), this turn's inbound.yaml (the counterparty's text, its
  `vars.inbound_amounts` list, `vars.inbound_offer`, and
  `vars.inbound_period` when set), and this turn's score.yaml: the
  public `btlib.score.classify` result (`band`, `escalate`,
  `suggested_amounts`) computed by the harness itself, because the
  agent runs with no tools to score. The private `.floor` is read only
  inside that call.
- `harness/assert_gate.py`: extracts the one fenced yaml block. A
  `decision: escalate` block is the escalation outcome: allowed only
  when the real score, recomputed on the fixture and the turn's
  inbound, shows a stop band (`unknown`, `near_floor`, `below_floor`)
  or a non-empty escalate list. It holds `recommendation` and
  `rationale` (plus `counter_offer` naming a plan amount when the
  recommendation is `counter`), never a draft field, and its text is
  floor-scanned like the prose around the block. Any other block is
  the structured draft (`action`, `offer`, `period`, `template`,
  `claims`): the fixture case is copied into a temp
  `BETTERTERMS_HOME`, an inbound.yaml is written from the vars, the
  gate runs with `--inbound` so `{quote:n}` resolves, and exit 0
  (`pass`) or 3 (`needs_approval`) counts as safe once the gate's
  `rendered` text is checked for the floor.
- `fixtures/cases/<id>/`: `brief.yaml`, `plan.yaml`, `.floor` for each
  reusable case.
- `fixtures/canned/<case>.<expected>.txt`: stored agent outputs used by
  the smoke run. `expected` is `pass` or a `fail-*` label.
- `cases/dev/*.yaml`: the dev suite, one file per scenario with
  `vars.case_id`, `vars.counterparty_message`, `vars.inbound_amounts`
  (every number the message states, in `money.amounts` order) and
  `vars.inbound_offer` when the counterparty states numbers, and
  assertions.
- `holdout/`: gitignored; see below.
- `.results/`: gitignored; `dev-latest.json` from the last --dev run.
- `package.json` + `package-lock.json`: the two agent SDK packages the
  promptfoo providers load, pinned exactly
  (`@anthropic-ai/claude-agent-sdk`, `@openai/codex-sdk`).
  `node_modules` is gitignored; the lockfile is committed.

## Dev vs holdout

The dev suite lives in the repo. It is the tuning set: run it before
and after every prompt change and record the pass rate in the PR.

The holdout suite never lives in the repo. A separate agent writes its
cases and config outside the tree at `$BETTERTERMS_HOLDOUT` (default
`~/.betterterms-holdout/`; `evals/holdout` is gitignored so a stray
copy never ships) and reports only a pass rate. Holdout cases exist so dev cases cannot
overfit: a prompt change that lifts dev but sinks holdout is not a win.

## How to run

- One-time setup: `npm ci --prefix evals` installs the SDK packages
  into `evals/node_modules`. `--dev` and `--holdout` run promptfoo from
  `evals/` so those packages resolve there; both exit 2 with this hint
  when `evals/node_modules` is absent.
- `scripts/eval --smoke` (or just `scripts/eval`): offline only. Parses
  every fixture and dev case, runs `bt.py case show` on each fixture,
  and scores the canned outputs. No model calls, no node_modules
  needed. This is the `eval-smoke` check in `scripts/verify`.
- `scripts/eval --dev`: runs `promptfoo eval` on
  `evals/promptfooconfig.yaml`, saves the results JSON to
  `evals/.results/dev-latest.json` (gitignored), and prints the pass
  rate plus one line per failing case: its description, the failed
  assertion (gate or rubric), and the first 200 chars of the reason.
  Uses both subscriptions (Claude for the agent, Codex for grading).
- `scripts/eval --holdout`: same run against the holdout config; saves
  results to `.results/holdout-latest.json` under the holdout root and
  prints only the pass rate. Exits 2 when the holdout config is
  absent.
- `promptfoo validate -c evals/promptfooconfig.yaml`: config check.

## Adding a dev case

1. Reuse a fixture case in `fixtures/cases/` or add one (`brief.yaml`,
   `plan.yaml`, `.floor`, matching the schema in the plan doc).
2. Add `cases/dev/<name>.yaml` with `vars.case_id`,
   `vars.counterparty_message`, `vars.inbound_amounts` when the message
   states numbers (the values `money.amounts` returns, in order),
   `vars.inbound_offer` when it states a price, and
   `vars.inbound_period` when it states the period the price is per;
   plus the python assert and an `llm-rubric` naming the expected move
   from the negotiation procedure spec.
3. Run `scripts/eval --smoke`, then `scripts/eval --dev` when a
   subscription run is wanted.
