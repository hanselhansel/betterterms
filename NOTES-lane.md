# NOTES, lane R5

Scope notes for reviewers. Implemented: three-tab cockpit pane (Cases,
Approvals, Savings), the AbovePrompt band, gate verdict rows, the
status line, inbound toasts, and the hash-bound approval flow. New
modules: `mod/lib/approvals.js`, `mod/ui/pane.js`, `mod/ui/band.js`,
`mod/ui/rows.js`, `mod/types/index.d.ts`. `plugin.json` names the types.

## Contract notes other lanes should know

- `$.state` keys under `betterterms-mod`: `tab` (1|2|3), `selected`
  (string|null), `approvals` (Record<full sha256, true>). `approvals`
  entries are consumed on read: a press plus the on-disk `.approved`
  marker lets exactly one identical resend pass `gate --approved`.
- Pane id `betterterms`; commands `/betterterms` and alias
  `/betterterms-cases` both open it.
- `## rejected` thread markers are stripped in
  `lib/cases.js:parseThreadAll` before `parse.js` sees the thread, so
  the reject marker never becomes a turn. `mod/lib/parse.js` itself is
  unchanged (outside the Files list).
- Held-card hotkeys `a`/`e`/`r` bind only when a single card is on the
  tab; with several held drafts the same letter could fire every card.
- `takeApproval` fails closed: a `$.state.set` that throws or reports
  `isSet: false` is not a take, so a resend denies instead of spending
  nothing and passing.

## Loader constraints that shaped the code

- `$` may be passed only to top-level functions declared in
  `register.js`; `$` or `$.fs` as a value crossing an import is
  refused. That is why `scanCases`, `runGate`, `runHeld`, `isCaseWrite`
  and the pane actions live in `register.js` and `lib/*.js` carries
  only pure helpers.
- `$.state` refs must be literal `{ plugin, key }` objects in
  `register.js` for the strict audit to enumerate reads/writes; they
  are deliberately not exported.
- `ui.ask` is a direct API, not an op event, so the autonomy-2 ask
  path cannot be wired in `claude plugin test`; it is covered by the
  node-side tests only.

## Deviations from the Files list

- `mod/approvals.test.tsx` is `.tsx`, not `.ts`: Node 24's
  `node --test` discovers `.test.ts` and cannot resolve the
  `claude-code/testing` import, which exists only inside the Claude
  runner. Same convention as `register.test.tsx`.
- `node --test mod` (directory arg) does not run on Node 24; the
  working form is `cd mod && node --test`. Documented in the README.
- `mod/testkit.js` gained state/prompt/status/write fakes and
  `mod/cases.test.js`, `mod/register.test.js` were updated for the
  held-draft semantics (the plan names the two new test files; the
  existing ones needed matching updates).
- `mod/README.md` and `mod/.claude-plugin/plugin.json` updated per the
  Files list.

## Out of scope, left for R6

Terms editor (`mod/ui/terms.js`), the scale drag client, and the
savings charts (`mod/ui/savings.js`, `mod/client/*`). The Savings tab
currently shows the ledger's `saved_per_year` total only.
