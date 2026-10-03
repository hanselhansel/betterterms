# NOTES: lane-6-refunds

Things outside this lane's Files list that the step or orchestrator owns.

- `pack-schema` verify check: the plan (Task 6.x) says `scripts/verify`
  gains `pack-schema`, but no such check exists in the current tree and
  `scripts/` is outside this lane. pack.yaml uses exactly the keys the
  plan names: name, command, mode, direction, triggers, intake,
  discovery, research, savings.
- `templates/pack/` contributor template: the plan assigns it to the
  "first lane". Not created here; it is outside this lane's Files list.
- Dev eval cases: only recorded as ideas at the end of playbook.md per
  the brief. The orchestrator turns them into evals/cases/dev files and
  decides whether the eval harness loads pack SKILL.md/references (the
  current harness only mounts exchange and guardrails files).
- Dropped claims kept out on purpose: the ~120-day card-network dispute
  window ([U] in research, not re-checked), the 22%/6% SaaS renewal
  figures (other packs), and naming merchants that ban disputes.
- ROSCA row in rights.md relies on the research doc's [V] tag on the
  Jones Day URL (read date recorded as the research date 2026-10-03).
  It was not in the re-check batch; orchestrator may want to re-verify.
- The gate's free-text scanner allows standalone integers 1 to 99, so
  templates use day counts ("14 days", "7 days") only; years and prices
  stay out of literal template text by design.
