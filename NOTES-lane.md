# Lane 9.1 notes

Findings that touch files outside the task's Files list. Not fixed here.

- Plan text says `mod/hooks/hooks.json` should carry
  `"modules": ["./register.js"]`. Claude resolves module paths relative
  to `hooks/hooks.json`, so the working value is `"../register.js"`.
  `claude plugin validate ./mod` fails on the `./` spelling and passes
  on `../`. `mod/register.test.js` pins the working value.
- `scripts/bump-version` syncs only generated outputs, so
  `mod/.claude-plugin/plugin.json`'s `version` field is hand-maintained
  and can drift from `VERSION`. Either teach bump-version to check it
  or drop the field.
- `claude plugin test` discovers only `*.test.ts`/`*.test.tsx`, while
  `node --test` discovers `.test.ts` and `.test.js` but not `.tsx`, and
  cannot resolve `claude-code/testing`. The engine-side tests live in
  `mod/register.test.tsx` so both runners pass. If the plan elsewhere
  assumes `claude plugin test` runs the node suite, it does not.
- `node --test <dir>` does not take a bare directory on Node 24; use a
  glob (`node --test 'mod/*.test.js'`) or bare `node --test`.
