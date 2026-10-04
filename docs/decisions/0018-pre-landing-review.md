# 0018. Pre-landing review: same-user limits and vendor semantics

Status: accepted. Amended by 0019. Date: 2026-10-05.

## Context

The 0.10.0 pre-landing review surfaced one class of findings that could
not be fixed by hardening alone: outside the mod, the agent runs as the
user, so a determined or prompt-injected agent can reach the same files
the user can. The owner approved stating the limits plainly rather than
shipping weaker half-measures.

## Decisions

- **Same-user limit (B).** `hooks/guard.py` is hardened (input
  normalization, scope to the betterterms home, whole-`bt.py`-call
  exemption) but README, the safety guide and SECURITY.md state plainly
  that it is best effort; only the mod's in-memory approval resists a
  determined agent. No signed-approval scheme: more code, still
  bypassable by the same user.
- **Walk-away in a Projects thread (C).** The terms widget keeps its
  walk-away field and now warns that the typed `bt floor` command stays
  in the thread where the model can read it later. The gate still
  blocks any draft stating the number. Removing the field would leave
  cloud users with no entry path at all.
- **Floor probing (D).** Documented: repeated `gate` calls could
  triangulate the walk-away. The skills' per-turn gate cap is the
  standing mitigation; a probe counter is a P1 TODO, not in this
  release.
- **Platform (E).** `bt.py` needs Unix file locking: macOS, Linux and
  WSL are supported, native Windows is not. `scripts/doctor` reports it.
- **Cloud persistence (F).** Cases under a cloud session's ephemeral
  home vanish with the VM; `hooks/session-start.sh` warns when
  `CLAUDE_CODE_REMOTE=true` and the betterterms home is under the
  session home.
- **Vendor semantics (G).** `scripts/vendor-into-repo` no longer copies
  skills when it enables the plugin (the plugin supplies them; a copy
  would load each skill twice) and warns about stale vendored copies.
  `--no-plugin` vendors the skills alone for sessions that cannot reach
  the marketplace.
