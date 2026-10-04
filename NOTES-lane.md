# Lane R7 notes

Things noticed while doing the widget fallback that sit outside the
task's file list.

- `skills/betterterms-guardrails/SKILL.md` still describes the
  pre-R3 approval flow: "Show the user the rendered text and the
  plain-word reasons, ask for an explicit yes, then re-run with
  `--approved`" and "`--approved` is only honest after the user's
  explicit yes". Since R3, `--approved` passes only when
  `held/<hash>.approved` exists for the exact rendered text, so that
  wording now describes a flow that cannot work. It also does not
  mention the `hash` field on `needs_approval` or the display modes.
  Worth an edit in R8 (docs), or sooner if another lane owns it.
- `docs/guides/quickstart.md` and `docs/guides/safety-model.md`
  predate held drafts and the typed commands; R8 owns docs.
- The widget buttons emit the spec 6.8 grammar (`bt approve`,
  `bt reject`, `bt floor`, `bt terms`), which R4's
  `hooks/prompt_commands.py` parses in a parallel lane. The terms
  widget sends only the keys whose fields are non-empty (for example
  `bt terms case-1 target=80` when the alternative field is left
  blank). If R4's parser requires both `target=` and `alternative=`,
  a single-field save fails; the grammar in the spec lists both keys
  but does not say whether each is optional.
- `bt.py widget cases` marks a case "case files unreadable" when its
  brief or plan fails to parse instead of sinking the whole listing;
  a corrupt `held/*.yaml` shows "held list unreadable" for the same
  reason.
