# NOTES lane r6

Out-of-scope items found while building R6 (terms editor + savings
charts). Noted here instead of fixed, per the task rules.

## `bt.py ledger total` has no `--json` flag

Spec 6.5 says numbers come from `bt.py ledger total --json`. The R3
CLI emits JSON unconditionally and rejects `--json` with
`unrecognized arguments`. The mod calls `bt.py ledger total` plain.
Either the spec line or the parser should get a `--json` alias later.

## Test file named `terms.test.tsx`, not `terms.test.ts`

The plan lists `mod/terms.test.ts`. Engine-side tests must end in
`.tsx` so `node --test` leaves them alone: they import
`claude-code/testing`, which only the engine resolves. Same pattern
as `register.test.tsx` and `approvals.test.tsx`.

## Support files the register split added

`mod/register.js` was exactly 400 lines. The strict audit follows `$`
only into the hooks module's own functions, so the move produced two
lib files, both named in the task's example ("for example into
mod/lib/wiring.js or mod/ui/*.js"):

- `mod/lib/hostio.js`: host-taking IO primitives (homeDir, readIf,
  statIf, listIf, findBt, runProc).
- `mod/lib/wiring.js`: every hook's work over the `host` facade
  (scan, gate, pane actions, session, command, poll).

## `.floor` read in ui/terms.js

The one deliberate read of `cases/<id>/.floor` by the mod lives in
`openTerms`, to show the user their walk-away in the pane (spec 6.4,
owner decision 2026-10-04). The value never reaches argv, `bt.py`
stdout, `$.state`, or any file; it leaves only as stdin to
`case set-floor`. The test `save writes walk-away through stdin,
never argv` asserts no argv element carries it.
