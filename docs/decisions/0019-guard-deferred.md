# 0019. Always-on file guard deferred: same-user enforcement does not hold

Status: accepted. Date: 2026-10-05.

## Context

Release 0.10.0 review rejected `hooks/guard.py` three times. The
`PreToolUse` hook, scoped to the betterterms home, denied agent reads
of `.floor` files, `held/` markers and the session log, and agent
writes under `held/`. In review it failed in both directions:

- It blocked legitimate work: first-case writes (`brief.yaml`,
  `plan.yaml`, `targets.yaml` under a new case dir), research source
  adds (`bt.py source add` records under `sources/`), and files in
  unrelated projects, since a `*` matcher runs the hook on every tool
  call in the session.
- It was bypassable anyway: the hook and the agent run as the same OS
  user, so a determined or prompt-injected agent can rewrite the hook,
  edit `hooks.json`, or reach the files through a path the matcher
  never saw.

0018 shipped it hardened as best effort. The third review concluded a
control that blocks the user's own work while remaining bypassable by
the agent it guards against is worse than stating the limit plainly.

## Decisions

- The `PreToolUse` guard leaves release 0.10.0: `hooks/guard.py`, its
  `hooks.json` entry and `tests/test_guard_hook.py` are removed.
  `hooks/prompt_commands.py` (typed `bt` commands), the session hook
  and `bt.py held disarm` stay.
- Docs state the boundary plainly: outside the mod, nothing technical
  stops the agent from reading the walk-away file or writing an
  approval marker if it tries. The skills instruct it never to, the
  gate blocks any draft that states the walk-away, and of the typed
  `bt` commands only `bt floor` is kept from the model where the
  prompt hook runs; `bt approve`, `bt reject` and `bt terms` are
  handled first and then passed through with a note. In the mod,
  approval comes only from a pane press or a `bt approve` the user
  types.
- A real boundary needs a mechanism that does not run as the agent's
  user: an OS-level separate user, or a keychain-held secret for the
  floor. That design is a P1 TODO, not in this release.
