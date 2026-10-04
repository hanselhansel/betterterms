# NOTES lane-r4

Task R4 (settings hooks, spec 6.8): done, tests and verify green.

Out-of-scope observations for later lanes:

- Docs: the typed commands (`bt approve`, `bt reject`, `bt floor`,
  `bt terms`) are not yet described in README or docs/guides; the
  docs lane (R8) should cover the chat-mode flow.
- `bt terms` grammar is fixed order (`target=` then `alternative=`),
  matching spec 6.8. Other orders block with the usage line.
- The guard denies any path with a `held/` segment, not only paths
  under `~/.betterterms/cases/`, per the spec wording "a `held/`
  path". An unrelated directory named `held/` would also be denied;
  the guard is best effort.
- The transcript-dir rule only fires when `transcript_path`'s parent
  is at least three path components deep, so a shallow path like
  `/tmp/x.jsonl` cannot wedge unrelated `/tmp` work.
