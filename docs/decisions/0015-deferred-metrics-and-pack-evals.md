# 0015. Deferred metrics and pack evals

Status: accepted (owner decision 2026-10-04). Date: 2026-10-04.

## Context

The negotiation procedure spec defines 12 metrics (section 8) plus
multi-turn simulated counterparties, and the pack plan defines 14 eval
cases, two per pack. Building all of it in this release would put the
metrics suite, the simulator, and 14 new eval cases in front of the
same reviewers and install tests that gate the core changes. The
release's promise is a kit a stranger can install and use end to end,
not a full measurement program.

## Decision

Defer to a later release, recorded here rather than built:

- The 12 metrics in the negotiation procedure spec, section 8.
- Multi-turn simulated counterparties.
- The 14 pack eval cases (2 per pack). Evals stay at the current 12
  cases.
- Optional anonymized response sharing. The README line offering it
  is removed; no collection code exists or ships.

What the release does keep: the existing 12-case eval (9 of 12 dev
target, holdout run by a separate agent), the ledger's recorded
savings, and `bt.py ledger total` as the only savings number the kit
claims.

## Consequences

`bt.py ledger` remains the only shipped measurement surface, so the
Savings tab and every savings claim in docs derive from files the user
owns. When metrics return they land as a new lane with their own
decision, reading the ledger and case folders rather than new runtime
state. The pack eval count stays 12 until that lane adds the 14 pack
cases, so eval verification targets do not change in this release.
