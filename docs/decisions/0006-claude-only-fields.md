# 0006. Claude-only fields: metadata flag is inert on Claude Code

Status: accepted. Date: 2026-10-03.

## Context

`betterterms-exchange` carries `metadata: {disable-model-invocation: "true"}` in its
SKILL.md frontmatter. The open Agent Skills format allows `metadata` as a string map; our
own `skill-names` check forbids any other top-level keys, so the flag cannot move to top
level without breaking the format every other host reads. Task 4.1 asked whether Claude
Code honors the flag from `metadata`, and if not, to record the gap instead of editing the
source.

## Findings (Claude Code 2.1.288)

- `disable-model-invocation` is read only from frontmatter top level
  (`frontmatter["disable-model-invocation"]`). `metadata` is on the recognized-key
  whitelist, so the file loads cleanly, but nothing inside it is consulted for invocation
  control.
- `skillOverrides` settings cannot substitute: the settings path returns early for skills
  whose `source` is `"plugin"`, so an installed plugin skill is always model-invocable.
- No `plugin.json` or marketplace field sets per-skill invocation policy.
- `claude plugin validate` (plain and `--strict`) passes our manifests, skills, and
  commands with no warnings about the metadata key.

## Decision

Keep `metadata: {disable-model-invocation: "true"}` in the SKILL.md source. It is the
only portable spelling of the intent and hosts that read metadata may honor it. Do not
generate a Claude-specific SKILL.md variant: a second copy of the skill would drift.

## Consequences

On Claude Code, the plugin-installed `betterterms-exchange` skill can be invoked by the
model, not only by the user. The flag is advisory hardening, not the safety boundary: the
coded gate (`bt.py gate`) blocks every send that crosses the floor, leaks the floor, or
carries an untraced claim, and autonomy levels plus the irreversible-action approval rule
hold regardless of who invoked the skill. Revisit if Claude Code starts honoring the
metadata form.
