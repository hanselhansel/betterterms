# NOTES-lane-7-promotion

Things the promotion lane noticed but did not do, because they sit
outside its file list.

- Eval cases are ideas only. The two dev eval cases for this pack
  are described under "Eval ideas" in
  `skills/betterterms-promotion/references/playbook.md`; the
  orchestrator owns the actual `evals/cases/dev/*.yaml` files and
  any `evals/fixtures/cases/<id>/` fixture for a promotion case.
- `evals/fixtures/cases/` has no `promotion/` fixture yet; the
  dev-case yaml cannot run until one exists (needs a brief, plan,
  and `.floor`).
- The `commands/promotion.md` host artifact comes from
  `scripts/build`; nothing to hand-write here.
- The sibling lane (`feat/lane-7-job-offer`, command `salary`)
  shares this step. No file overlap; the `promotion` command slug is
  unique against existing packs.
- Savings formula is `(after - before) * periods_per_year`
  (receive direction), matching `btlib/ledger.py` line 62. All
  existing packs are pay direction and use the reverse; this is the
  first receive-direction pack.yaml, so the convention now differs
  by direction. Worth a line in `templates/pack/pack.yaml` later.
