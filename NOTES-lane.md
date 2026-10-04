CURRENT_WORKING_FILE: scripts/vendor-into-repo

Notes for the orchestrator (out of this lane's Files list):

- docs/specs/2026-10-03-betterterms-design.md line ~230 still offers
  "upload skill zips to the claude.ai account" for cloud sessions. Skill
  zips were removed in R1; the line is stale and could join the settings
  wording now in docs/guides/install.md.
- scripts/vendor-into-repo sets enabledPlugins["betterterms@betterterms"]
  to true even when the user previously set it false in the target repo.
  --no-plugin is the documented opt-out; flagged in case a "never
  override an explicit false" rule is preferred.
