# Lane notes (task 2.2, core skills)

- `skills/.gitkeep` is now redundant: `skills/` holds nine real skill
  folders. Removing it is outside this task's file list, so it stays.
  Safe to delete in a later step.
- Task 5.1 will need a home for discovery's target record format. This
  lane writes candidate targets to `targets.yaml` in the case folder with
  the fields named in the plan (`counterparty`, `amount`, `cadence`,
  `renewal_date`, `evidence`, `usage_signal`). Task 5.1 owns the
  authoritative record definition in `references/target-record.md`.
- `bt.py` does not exist yet (lane A builds it). The skills call it
  exactly as specified in Shared interfaces, so nothing here runs until
  lane A lands.
