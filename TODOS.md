# TODOS

## Dev tooling (scripts/)

Deferred from the step 1 ship (owner approved 2026-10-03), to fix first in step 2.

## Completed

- **Priority:** P2. bump-version rollback: refuse non-regular-file targets before writing; attempt every restore, list failures, re-raise the original error. (scripts/bump-version:92-96) **Completed:** step 2
- **Priority:** P2. build: refuse any path segment equal to `.git` (case-insensitive), not only the first. (scripts/build:38) **Completed:** step 2
- **Priority:** P2. build: reject generated paths that change under normalization; dedupe on the normalized, lower-cased form. (scripts/build:66) **Completed:** step 2
- **Priority:** P3. checks_scan.display(): decode with backslashreplace so non-ASCII names do not crash. (scripts/_lib/checks_scan.py:222) **Completed:** step 2
- **Priority:** P3. build: generators may not write VERSION or kit.config.json. **Completed:** step 2
- **Priority:** P3. prose-rules: inflected banned words (crucially, robustness). (scripts/_lib/checks_prose.py:18-22) **Completed:** step 2
- **Priority:** P3. no-local-paths: catch home paths in parentheses and quotes; lookahead (?![\w.-]). (scripts/_lib/checks_files.py:37) **Completed:** step 2
- **Priority:** P3. skill-names: use fullmatch so a trailing newline fails. (scripts/_lib/checks_skills.py:11,72) **Completed:** step 2
- **Priority:** P3. Scan decoded frontmatter strings for banned words and local paths (escaped \u sequences). (checks_prose.py:52, checks_files.py:84) **Completed:** step 2
- **Priority:** P3. no-symlinks vs evals/holdout: drop the symlink suggestion from the plan and evals README; .gitignore entries without trailing slash; apply _skipped to the full path. **Completed:** step 2
- **Priority:** P3. Tests for the symlink guards in checks_prose._data_files and check_skill_names. **Completed:** step 2
- **Priority:** P3. checks_files.py module docstring lists the symlink check. **Completed:** step 2
- **Priority:** P4. verify ROOT pointing at another repo runs its tests (document or restrict); bump-version accepts same or lower version silently. **Completed:** step 2
