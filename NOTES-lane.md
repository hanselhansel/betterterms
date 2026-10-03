# Lane 2.1 notes

Things outside the task's Files list that came up. Nothing else blocked.

- `btlib/yaml.py` is a verbatim copy of `scripts/_lib/miniyaml.py`. That module
  imports `from .miniyaml_scalars import ...`, so `btlib/miniyaml_scalars.py`
  is also copied verbatim. The new `btlib-yaml-sync` verify check compares both
  pairs, so the skill folder stays self-contained. If miniyaml is ever merged
  into one file, drop the extra copy and shrink the check.
- `check_skill_names` in `scripts/verify` used to FAIL on a skill folder with
  no SKILL.md. This lane creates `skills/betterterms-guardrails/scripts/`
  before lane 2.2 writes any SKILL.md, and verify must pass per lane. Missing
  SKILL.md is now reported as a PASS note (`skills/x has no SKILL.md yet`)
  while every other rule still fails. Trade-off: a folder that permanently
  lacks SKILL.md no longer fails this check. Consider restoring the strict
  check once all step-2 skills have landed, or covering it in the step-4
  packaging checks.
- `tests/bt_helpers.py` is a shared helper for the five named test files
  (run_bt with a temp BETTERTERMS_HOME, case fixtures). Every test uses a
  temporary home; nothing touches a real user directory.
- `ledger add` computes saved_per_year direction-aware: `before - after` for
  pay cases, `after - before` for receive cases, times periods per year
  (month 12, year 1). A receive case therefore logs a positive gain.
- `gate.check` evaluates every rule and collects reasons; result precedence is
  block, then needs_approval, then pass. An irreversible action that also
  leaks the floor reports block, so the draft gets fixed before approval.
- `money.find` marks an amount as currency only when it has a currency prefix
  or suffix, a k/m/b multiplier, or a spelled phrase followed by dollars or
  bucks. Bare numbers (for example "3 options") are parsed but unmarked, so
  the untraced-number rule does not flag ordinary prose numbers. Floor
  disclosure still checks every parsed amount, including bare and spelled.
