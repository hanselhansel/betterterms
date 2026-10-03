# 0002. Packs are sibling skills under skills/

Status: accepted. Date: 2026-10-03.

## Context
The spec puts packs in `packs/<name>/`. Packs and core skills must call the runtime tool. Install
layouts differ: repo tree, Claude plugin root, flat `~/.agents/skills`, vendored `.claude/skills`.
A path that works in one layout breaks in another.

## Decision
Every skill, core or pack, is a folder `skills/betterterms-<x>/`. The runtime tool lives in
`skills/betterterms-guardrails/scripts/bt.py`. Every skill calls it as
`python3 ../betterterms-guardrails/scripts/bt.py`. The contributor template moves to
`templates/pack/`.

## Consequences
One relative path works in every layout. Packs keep their own `pack.yaml` and `references/`.
Pack commands such as `/betterterms:salary` come from generated `commands/` files.
