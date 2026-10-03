# Changelog

## [0.1.0] - 2026-10-03

### Added
- Design spec, negotiation procedure spec, research notes, the v1 implementation plan, and decision records 0001 to 0005.
- `python3 scripts/verify`, one local command that runs the unit tests and every repo check: skill names and frontmatter, no `bin/`, no `CLAUDE.md`/`AGENTS.md`, no local paths, no symlinks, prose rules (no em dashes, banned words), file size, vendored-code sync, generated-file freshness and version sync. Claude and Gemini plugin validation run when those CLIs are installed.
- `scripts/build` and `scripts/bump-version`, the generator registry and version tool that later steps use to write each host's manifests from one `VERSION`.
- A YAML layer built on bundled pure-Python PyYAML 6.0.3, so the toolkit needs no installs. It rejects duplicate keys, aliases and merge keys and reports errors with line numbers.

### Changed
- The YAML layer replaced an earlier hand-written parser that disagreed with real YAML on edge cases.
- `scripts/build` never deletes files and refuses unsafe write paths.
