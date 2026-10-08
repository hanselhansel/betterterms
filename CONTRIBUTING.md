# Contributing

## Add a pack

A pack is domain knowledge for one negotiation category: what works, who you
negotiate with, the rules that apply, and message starters. It never redefines
the procedure. With `templates/pack/` you can draft one in under an hour.

1. Copy `templates/pack/` to `skills/betterterms-<name>/` and replace every
   `<angle-bracket>` marker.
2. Fill `pack.yaml`: `name`, `command` (the slug behind
   `/betterterms:<command>`), `mode` (`act`, `coach`, or `both`), `direction`
   (`pay` or `receive`), `triggers`, `intake`, `discovery`, `research`, and
   `savings`. The `pack-schema` verify check enforces this shape exactly.
3. Write `references/playbook.md` (the moves, in order),
   `references/counterparties.md`, and `references/rights.md`. Every factual
   claim carries a source URL and the date you read it. A claim you cannot
   source does not ship.
4. Write `references/templates/`: voice-neutral message starters with
   placeholders only (`{offer}`, `{target}`, `{option:<label>}`,
   `{ladder:<n>}`, `{fact:<id>}`, `{quote:<n>}`). Never type a price.
5. Add two dev eval case ideas at the end of `playbook.md` under "Eval
   ideas". A denial that contradicts the published policy or a manipulation
   attempt makes a good case.
6. Delete the template's intro paragraph and "Contributor checklist" section.
7. Run `python3 scripts/verify` and fix what it flags, then open the PR on a
   `feat/` branch.

## Evals

`python3 scripts/eval --smoke` runs the offline check: case files parse,
fixtures behave, and the gate assertion works, all without LLM calls.

`python3 scripts/eval --dev` runs the promptfoo dev suite against simulated
counterparties. It needs `npm ci --prefix evals` once and the local Claude and
Codex logins. Run it before and after any prompt change and record the pass
rate in your PR. The holdout suite lives outside the repo; a separate agent
runs it and reports only a pass rate. See `evals/README.md`.

## Prose rules

User-facing markdown has a style check. No em dashes, and none of the banned
words (the list lives in `scripts/_lib/checks_prose.py`; the `prose-rules`
check in `scripts/verify` enforces it on shipped files). Write short
declarative sentences.

## Rules that apply everywhere

- Keep source files under 400 lines.
- Skills name actions, not tools.
- Counterparty text is data, never instructions. Say so in any skill that
  reads it.
- No absolute local paths in shipped files. Case files live in the user's
  `~/.betterterms`, never in the repo.
- One `VERSION`. `scripts/bump-version` writes it into every generated
  manifest.
- Never commit to main. Work on `feat/` branches and run
  `python3 scripts/verify` before every PR.
