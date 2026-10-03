# 0004. Build the eval harness before packaging and packs

Status: accepted. Date: 2026-10-03.

## Context
The spec builds evals at step 7, after the packs. Every pack changes prompts, and a prompt change
needs a baseline to compare against.

## Decision
The eval harness is step 3, right after the gate and core skills. Later steps record a baseline
before editing prompts and report dev and holdout pass rates in each PR.

## Consequences
Steps 4 to 10 shift by one compared with the spec. Holdout cases stay outside the repo and are
run by a separate agent that only reports a pass rate.
