# 0001. Floor lives in a separate file

Status: accepted. Date: 2026-10-03.

## Context
The design spec puts the floor in `plan.yaml` and says only the gate reads it. Skills read
`plan.yaml` to get the target, options, and facts, so an agent with file access would see the
floor every turn.

## Decision
The floor is stored in `cases/<id>/.floor` (mode 0600), written by `bt.py case set-floor` from
stdin. Only `bt.py gate` and `bt.py score` read it. `bt.py case show` never prints it.

## Consequences
Skills can read `plan.yaml` freely. The model still hears the floor once during intake; the
intake skill tells it not to repeat it, and the gate blocks any draft that contains it.
