# Source record

One file per finding in the case's `sources/` directory, written by
`bt.py source add`. The record is the evidence behind a claim; a draft
may only assert what traces back to one, or to something the user said.

## Fields

| Field | Content |
|---|---|
| `url` | Where the finding was read |
| `read_at` | ISO date it was read |
| `quote` | The exact text the claim rests on, copied verbatim |
| `trust` | `official`, `regulator`, `press`, or `forum` (see `trust-levels.md`) |
| `used_for` | What the finding supports in the case |

All five fields are required. The tool rejects anything missing,
misspelled, or outside the trust list.

## Storing a record

Pipe the record on stdin:

```
python3 ../betterterms-guardrails/scripts/bt.py source add <case_id>
```

It prints `{"id": "<n>", "path": ...}` and writes `sources/<n>.yaml`.
Inspect what is stored:

```
python3 ../betterterms-guardrails/scripts/bt.py source list <case_id>
python3 ../betterterms-guardrails/scripts/bt.py source stale <case_id> --days 90
```

A record in `stale` output is too old to rely on; read the source again
and store the fresh finding before using it.

## From record to plan fact

A draft may only cite facts on `plan.yaml`'s `facts` list. Each fact is:

- `id`: a short id the plan assigns, like `f1`
- `text`: the claim, verbatim from the record's `quote`
- `source`: the source record id (the `<n>` in `sources/<n>.yaml`), or
  `user statement` when the claim is something the user said

For each finding a draft may need, propose a fact for the plan step to
adopt. Keep `text` verbatim: the gate renders `{fact:<id>}` exactly as
written, and fact text that holds money reaches a message only through
that placeholder. Never copy the amount into a draft's free text; the
gate blocks it.
