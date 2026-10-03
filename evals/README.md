# betterterms evals

Simulated counterparties score the exchange skill. The agent under test
is a Claude agent (subscription, via the local Claude Code login,
provider `anthropic:claude-agent-sdk` with no tools). Grading rubrics run
on the Codex subscription (provider `openai:codex-sdk`, read-only
sandbox). The safety check is `assert_gate`, a python assertion that
runs `bt.py gate` on the draft and also fails when the floor appears
anywhere in the output.

Layout:

- `promptfooconfig.yaml`: prompt function, agent provider, grader.
- `harness/agent_prompt.py`: builds the system prompt from the exchange
  and guardrails skills plus the output contract, and returns it via
  `config.custom_system_prompt` so it lands in the provider's real
  system slot. The user prompt carries the fixture case files (never
  the floor) and the counterparty message.
- `harness/assert_gate.py`: extracts the one fenced yaml block, copies
  the fixture case into a temp `BETTERTERMS_HOME`, writes an
  inbound.yaml from `vars.counterparty_message` (plus
  `vars.inbound_offer` when set), runs the gate with `--inbound`, and
  treats exit 0 (`pass`) or 3 (`needs_approval`) as safe.
- `fixtures/cases/<id>/`: `brief.yaml`, `plan.yaml`, `.floor` for each
  reusable case.
- `fixtures/canned/<case>.<expected>.txt`: stored agent outputs used by
  the smoke run. `expected` is `pass` or a `fail-*` label.
- `cases/dev/*.yaml`: the dev suite, one file per scenario with
  `vars.case_id`, `vars.counterparty_message`, `vars.inbound_offer`
  when the counterparty states a price, and assertions.
- `holdout/`: gitignored; see below.

## Dev vs holdout

The dev suite lives in the repo. It is the tuning set: run it before
and after every prompt change and record the pass rate in the PR.

The holdout suite never lives in the repo. A separate agent writes its
cases and config outside the tree at `$BETTERTERMS_HOLDOUT` (default
`~/.betterterms-holdout/`, symlinked from `evals/holdout/` if wanted)
and reports only a pass rate. Holdout cases exist so dev cases cannot
overfit: a prompt change that lifts dev but sinks holdout is not a win.

## How to run

- `scripts/eval --smoke` (or just `scripts/eval`): offline only. Parses
  every fixture and dev case, runs `bt.py case show` on each fixture,
  and scores the canned outputs. No model calls. This is the
  `eval-smoke` check in `scripts/verify`.
- `scripts/eval --dev`: runs `promptfoo eval -c
  evals/promptfooconfig.yaml` and prints the pass rate. Uses both
  subscriptions (Claude for the agent, Codex for grading).
- `scripts/eval --holdout`: same run against the holdout config. Exits
  2 when the holdout config is absent.
- `promptfoo validate -c evals/promptfooconfig.yaml`: config check.

## Adding a dev case

1. Reuse a fixture case in `fixtures/cases/` or add one (`brief.yaml`,
   `plan.yaml`, `.floor`, matching the schema in the plan doc).
2. Add `cases/dev/<name>.yaml` with `vars.case_id`,
   `vars.counterparty_message`, `vars.inbound_offer` when the message
   states a price, the python assert, and an `llm-rubric`
   naming the expected move from the negotiation procedure spec.
3. Run `scripts/eval --smoke`, then `scripts/eval --dev` when a
   subscription run is wanted.
