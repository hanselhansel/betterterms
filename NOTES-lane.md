# Lane notes: lane-6-ai-api

Items outside this lane's Files list that the orchestrator may need.

- `scripts/verify` has no `pack-schema` check yet. The plan (step 6)
  says verify gains it. This lane's `pack.yaml` follows the documented
  shape: `name, command, mode, direction, triggers, intake, discovery,
  research, savings`.
- `templates/pack/` (the contributor template) was not created. The
  plan assigns it to "the first lane"; it is outside this lane's Files
  list.
- No test files were named in this task. Verification here is
  `python3 -m unittest discover -s tests` plus `python3 scripts/verify`
  (`skill-names`, `prose-rules`, `no-local-paths` cover the new files).
- No eval case files were added; the plan asks for two eval ideas in
  `references/playbook.md` (see "Eval ideas") for the orchestrator to
  turn into cases.
- `commands/ai-api.md` is a generated file produced by `scripts/build`
  from `pack.yaml`'s `command` key. Generators do not exist yet
  (`scripts/build` GENERATORS is empty), so nothing was generated here.
