# Eval baselines

Every change to skills, prompts, or graders reports both numbers against these.

| Date | Commit | Dev (12 cases) | Holdout (12 cases) | Notes |
|---|---|---|---|---|
| 2026-10-03 | 3e98c18 | 9/12 (75.0%) | 10/12 (83.3%) | First live run. Agent: Claude Agent SDK on the owner's Claude subscription. Grader: Codex SDK on the owner's Codex subscription. Dev failures: two job-offer cases, one piano-sale case. |

The holdout cases live outside the repo and are run by a separate agent that reports only its pass rate.
