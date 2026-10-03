# 0005. Bundle PyYAML instead of a hand-written YAML subset

Status: accepted (owner confirmed 2026-10-03). Date: 2026-10-03.

## Context
Specs store case files and SKILL.md frontmatter as YAML, and the toolkit must run with Python 3
stdlib only, so step 1 shipped a hand-written YAML subset. Three pre-landing review rounds found
30, 19, then 15 inputs where it disagreed with real YAML. Patching per input did not converge,
and /ship stops after three fix cycles.

## Decision
Vendor pure-Python PyYAML 6.0.3 (MIT) under `scripts/_lib/_vendor/yaml/`, and copy it into the
guardrails skill's `btlib/_vendor/yaml/` so the skill folder stays self-contained. `miniyaml` is a
thin wrapper (safe_load, safe_dump, duplicate-key rejection, errors with line numbers). The C
extension is not used. A `vendor-sync` verify check keeps the two copies identical.

## Consequences
About 5,900 lines of third-party code in `_vendor/`, exempt from the 400-line and prose checks.
YAML 1.1 rules apply (`yes`/`no` are booleans). Users still install nothing.
