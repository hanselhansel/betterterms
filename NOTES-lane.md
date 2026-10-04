# NOTES, lane R3

Scope notes for reviewers. Implemented: `bt.py where`, `bt.py config
show|set`, `bt.py case set-terms`, `bt.py held list|approve|reject`,
held drafts on `needs_approval`, and hash-bound approvals consumed by
`gate --approved`. New modules: `btlib/config.py`, `btlib/held.py`,
`btlib/cli_extra.py`. Decision record: `docs/decisions/0014-config-yaml.md`.

## Contract changes other lanes should know

- `bt.py gate --approved` no longer passes on the flag alone. The gate
  now requires a matching `held/<sha256>.approved` file (written by
  `bt.py held approve`, the mod, or the `bt approve` prompt hook in
  R4), consumes it once, and reports `no approval recorded for this
  exact text` when it is missing. `gate.check` keeps its signature.
- `needs_approval` gate output gains a `hash` field (sha256 of the
  rendered text) and writes `held/<hash>.yaml` into the case folder.
- On a block, the gate now drops every approval finding, not only the
  floor-adjacent ones the old `DROP_ON_BLOCK` named. A blocked draft
  has no approval path, so block reasons stay limited to block
  findings. This preserved the `[LIMITS]` assertions.
- `mod/` is unchanged per the Files list, but its current
  needs-approval flow (ask, then re-gate with `--approved`) now always
  denies until R5 wires the approval write: `node --test` still passes
  because it mocks the gate, yet the live send path cannot approve a
  held draft between R3 and R5 landing.
- `held reject` appends `## rejected <time> <hash>` to `thread.md`,
  which does not match the mod's `## in|out` entry grammar; R5 may
  want its own record shape.
- Test-only change outside the Files list, forced by the contract:
  the `gate()` helpers in `tests/bt_helpers.py` and 14 test files
  route `approved=True` through `approve_held`, which performs the
  hold-then-approve ritual a user would (`gate` once to hold, `held
  approve`, then the real `--approved` call). No test assertions were
  weakened.
- Config `autonomy` accepts 1 to 4, not the 0 to 4 the spec comment
  shows: brief `autonomy` validates 1 to 4, so 0 would only create
  cases the gate refuses. Noted in decision 0014.
