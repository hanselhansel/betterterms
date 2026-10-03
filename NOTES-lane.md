# Lane 5.1 notes

- `evals/fixtures/cases/*/plan.yaml` write fact `source` as a URL or
  `user statement`. The new contract makes `source` a `sources/<n>.yaml`
  record id (or `user statement`). Nothing breaks: the gate never reads
  `source`. A later lane or the orchestrator may want the fixtures
  updated to record ids for consistency with
  `skills/betterterms-research/references/source-record.md`.
- `betterterms-plan` SKILL.md still says facts link to "a source record
  or a user statement" without naming the record-id form; same fix
  window as the fixtures.
