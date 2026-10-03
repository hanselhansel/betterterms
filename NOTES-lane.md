# NOTES lane-6-bills

Out-of-scope observations from the bills lane. Nothing here was done;
each item belongs to another lane or the orchestrator.

- `pack-schema` check: the plan says step 6 adds a `pack-schema` check
  to `scripts/verify`. The CHECKS registry in this worktree's
  `scripts/verify` has no such check, and `scripts/` is outside this
  lane's Files list. `skills/betterterms-bills/pack.yaml` was written
  to the documented key set (name, command, mode, direction, triggers,
  intake, discovery, research, savings) and parses with
  `scripts/_lib/miniyaml.py`.
- `templates/pack/` (the contributor pack template) does not exist in
  this worktree. The plan assigns it to the first step-6 lane; this
  lane's Files list covers only `skills/betterterms-bills/`.
- No test files were named in the lane brief, so none were written.
  Templates were verified by running each `text` block through
  `btlib/render.scan_free_text` and `render.agreement_word` directly
  (all pass), and `pack.yaml` and `SKILL.md` through `miniyaml` and
  `frontmatter`.
- `scripts/build` in this base has an empty GENERATORS list, so a new
  `pack.yaml` cannot break `build-fresh` here. When the packaging
  generators land, `commands/bills.md` will need `command: bills`
  from this pack's `pack.yaml`, which is present.
