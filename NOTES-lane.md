# NOTES: lane 6, subscriptions pack

For the orchestrator and sibling pack lanes.

## pack-schema check semantics (scripts/_lib/checks_packs.py)

Registered in `scripts/verify`. It validates every
`skills/betterterms-*/pack.yaml` (top level of each skill folder only)
and SKIPs when none exist. The contract it enforces, straight from the
plan's pack.yaml keys:

- Exactly these keys: `name`, `command`, `mode`, `direction`,
  `triggers`, `intake`, `discovery`, `research`, `savings`. Extra or
  missing keys FAIL.
- `name`: slug `[a-z0-9-]+` that must equal the folder suffix after
  `betterterms-` (the value passed to `bt.py case new --pack`).
- `command`: slug, unique across all packs.
- `mode`: `act`, `coach`, or `both`. `direction`: `pay` or `receive`.
- `triggers`, `intake`: non-empty lists of non-empty strings.
- `discovery`: a list (may be empty); each entry is a mapping with
  exactly `source`, `find` (non-empty strings) and `window_days`
  (positive integer).
- `research`: a list (may be empty); each entry is a mapping with only
  `kind`, one of `policy`, `pricing`, `precedent`, `rights`, `market`
  (the design spec's list).
- `savings`: a mapping with only `formula`, a non-empty string.

If a lane needs a new research kind or another nested key, widen the
enum in `checks_packs.py` in that lane and say so in the PR; do not
ship a pack.yaml that fails the check.

## Lane scope notes

- `scripts/build` does not yet consume `pack.yaml` `command`
  (commands/<command>.md generation is step 4). Nothing to do here.
- `templates/pack/` is a contributor skeleton, not a skill; verify
  checks ignore it except prose-rules, no-local-paths, and file-size.
- The intake list in pack.yaml holds only the category questions from
  procedure spec section 3; the core question bank stays in
  betterterms-intake.
