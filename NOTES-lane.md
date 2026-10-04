# Lane R1 notes

Deviations and findings for the orchestrator:

- The removal test greps tracked files for the removed names. The
  plan exempts CHANGELOG.md and docs/decisions/; the test also
  exempts docs/plans, docs/specs, docs/research and TODOS.md, the
  same INTERNAL_DOCS set checks_scan already carves out. Required
  because the release plan and spec name the removed things by
  design, and dated records keep their mentions like the CHANGELOG.
- The bare-word scan forced rewording beyond the Files list:
  the removed rules word also appeared in SKILL.md files, other
  pack references, and generated commands. Every instance was
  reworded to "state or country" / "where the user lives or
  works"; the sourced rules themselves were kept, only the
  by-place framing changed. commands/ regenerated via scripts/build.
- No pack rights.md line actually promised per-country call or
  recording rules. The only such promises were the old spec's
  rules-directory row and config key, both now removed.
- The two generated plugin manifests in the removed dot-directories
  were deleted along with their generators (spec: "delete the code,
  manifests").
- Left for later lanes on purpose: mentions inside docs/plans,
  docs/specs (other than the two required edits), docs/research,
  CHANGELOG history, and decision 0011 (a dated record).
