# Lane 4.1 notes

Handoff items for the orchestrator and later lanes. Nothing here was done
because the files are outside this task's Files list.

- `tests/test_scripts.py` `make_repo` copies scripts/, VERSION and
  kit.config.json but not skills/ or the generated manifests. The generators
  return `{}` on any root without a `skills/` directory so the existing
  `build --check` smoke tests stay green. Step 8 generators
  (`gen_{gemini,cursor,muse,agent_plugins}.py`) should keep the same gate.
- `GENERATORS = []` in `scripts/build` stays a literal empty list because
  tests rewrite that exact line to stub generators; real generators are
  appended on the next line. Do not fold them into one literal.
- `.codex-plugin/plugin.json` `interface` block and
  `.agents/plugins/marketplace.json` `policy`/`source` shape are modeled on
  superpowers 6.4.2, since Codex docs do not publish a schema. Task 4.2's
  `codex plugin marketplace add ./` + `codex plugin add` install test is the
  real check.
- `claude plugin validate .` validates the marketplace manifest; the plugin
  manifest and `skills/`/`commands/` dirs validate separately and all pass,
  including `--strict`.
- `install-skills --copy` and `vendor-into-repo` write a
  `.betterterms-version` marker into the target skills dir; `doctor` reads it
  to flag stale copies and treats a copied skill without the marker as a
  finding.
- `hooks/hooks.json` matcher covers `startup|resume|clear|compact`. If Claude
  Code adds SessionStart matchers, the hook should be widened or the matcher
  dropped.
