# 0014. config.yaml and hash-bound approvals

Status: accepted (release lane R3, spec 5 and 6.3). Amended by 0019
and 0020: the PreToolUse guard section C names is deferred, and the
`.approved` marker is the only consent record in every display mode.
Date: 2026-10-07.

## Context

Section 5 adds a user config file the intake flow reads when it
creates a case, and section 6.3 makes the user the only actor who can
approve a held draft: a keypress in the mod or a `bt approve` message
caught by the prompt hook. Both need runtime support in `bt.py`: a
config read/write path, a held-draft record that survives restarts,
and an approval that binds to the exact rendered text it covers.

## Decision

A. `~/.betterterms/config.yaml` holds `autonomy`, `currency`,
   `sign_off` and `voice_notes`, mode 0600, written atomically like
   the floor file. `bt.py config show` prints the merged config and
   `bt.py config set <key> <value>` writes one key. An unknown key in
   the file is ignored with a stderr warning; an unknown key on
   `config set` is an error. A bad value stops the read with a plain
   error naming the key. Only `case new` applies it, to the new
   case's `autonomy` and `currency`; the mode defaults stand when no
   file exists. The gate, the scorer and the approval path never read
   it. The accepted `autonomy` range is 1 to 4 even though the spec
   comment says 0 to 4: brief `autonomy` validates 1 to 4, so a
   config value of 0 could only produce cases the gate refuses
   forever, and a bad value must fail at intake instead.

B. A `needs_approval` draft is held on disk: the gate writes
   `held/<sha256>.yaml` (rendered text, reasons, `held_at`) beside the
   case files, 0600 under a 0700 `held/` directory, and the gate JSON
   gains a `hash` field so a caller can name the draft. `bt.py held
   list` returns the records oldest first for the Approvals tab to
   rebuild after a restart.

C. An approval is `held/<hash>.approved`, written only by a user
   action: `bt.py held approve <id> <hash8>`, the mod, or the `bt
   approve` prompt hook. `bt.py gate --approved` no longer skips the
   review tier by itself: it passes only when an approval file
   matches the newly rendered text's hash, and it consumes the file
   and the held record after one use. With `--approved` and no
   matching file the draft is held again with the reason `no approval
   recorded for this exact text`. A forged file under `held/` is the
   PreToolUse guard's job (spec 6.8); inbound text can still never
   approve. `hash8` is a prefix of 8 to 64 hex chars and must match
   exactly one held draft: zero or several is exit 2, and several
   names every full hash.

D. `bt.py held reject <id> <hash8>` removes the held draft and any
   approval for it and appends a `## rejected <time> <hash>` line to
   `thread.md`. A rejected draft cannot be sent: its approval file is
   gone, so `--approved` holds it again.

E. `plan.yaml` gains `best_alternative` (`amount`, `period`, `note`),
   written by `bt.py case set-terms`, which never reads or writes
   `.floor`. The gate validates the field's shape like a fact's
   (`amount` a positive number or null, `period` a known period) but
   never compares it to the floor: it is context for the agent, not
   an offer (spec 6.4). `bt.py where` prints the runtime's own
   absolute path so skill instructions resolve `bt.py` at run time
   instead of a stored relative path.

## Layout

`btlib/config.py` owns the file, `btlib/held.py` owns the held and
approval records, and `btlib/cli_extra.py` owns the new subcommands so
`bt.py` stays under the file cap. `gate.check` keeps its signature;
`approved=True` now only asks for a matching approval file, never
skips a finding.
