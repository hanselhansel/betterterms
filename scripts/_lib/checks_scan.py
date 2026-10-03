"""Shared file-scanning machinery for the repo verification checks.

Most checks scan the same file list, computed once per verify run: the
git file list when the root is a git repo, os.walk otherwise, filtered
by the skip rules below. The exception is vendor-sync, which walks the
two copied trees on disk directly.
"""

import codecs
import functools
import os
import subprocess
from pathlib import Path

# SKIP_DIRS_TOP applies only to direct children of the root; SKIP_PATHS
# holds exact prefixes: .claude is scanned but .claude/worktrees is not,
# and evals/holdout is skipped in git mode and in the os.walk fallback.
SKIP_DIRS_ANYWHERE = {".git", "__pycache__", "node_modules"}
SKIP_DIRS_TOP = {
    ".venv", "venv", "dist", "holdout", ".idea",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".promptfoo",
}
SKIP_PATHS = {(".claude", "worktrees"), ("evals", "holdout")}

# Internal docs quote prose and local paths freely, so prose-rules and
# no-local-paths skip them; docs/guides and shipped files ARE checked.
# Vendored code is verbatim, so paths under the known _vendor roots are
# exempt from file-size, prose-rules and no-local-paths. Any other
# directory that happens to be named _vendor IS checked.
INTERNAL_DOCS = {
    ("docs", "research"), ("docs", "specs"),
    ("docs", "plans"), ("docs", "decisions"),
}
VENDOR_ROOTS = {
    ("scripts", "_lib", "_vendor"),
    ("skills", "betterterms-guardrails", "scripts", "btlib", "_vendor"),
}

SUBPROCESS_TIMEOUT = 120

# OS cruft and editor swap files never take part in comparisons.
JUNK_NAMES = {".DS_Store"}
JUNK_SUFFIXES = (".swp", ".swo", ".swn", "~")

# UTF-16 and UTF-32 byte-order marks: a file starting with one holds
# text, just not UTF-8.
_UTF_BOMS = (
    codecs.BOM_UTF32_LE,
    codecs.BOM_UTF32_BE,
    codecs.BOM_UTF16_LE,
    codecs.BOM_UTF16_BE,
)

# Suffixes that name a file as text; an extensionless entry point under
# scripts/ counts too. Binary bytes inside a text-named file are an
# error, not a skippable binary.
TEXT_SUFFIXES = {".md", ".py", ".js", ".json", ".yaml", ".yml", ".txt", ".toml"}


class BinaryFileError(Exception):
    """A text-named file holds NUL bytes."""


def is_internal_doc(rel):
    return any(rel.parts[: len(skip)] == skip for skip in INTERNAL_DOCS)


def is_vendor(rel):
    return any(rel.parts[: len(v)] == v for v in VENDOR_ROOTS)


def _skipped(parts):
    """Whether directory parts hit a skip rule."""
    return bool(parts) and (
        parts[0] in SKIP_DIRS_TOP
        or any(part in SKIP_DIRS_ANYWHERE for part in parts)
        or any(parts[: len(s)] == s for s in SKIP_PATHS)
    )


def git_relpaths(root):
    """Tracked plus non-ignored untracked files when root is a git repo;
    None otherwise, so callers fall back to os.walk."""
    if not (root / ".git").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.split("\0") if r.returncode == 0 else None


@functools.cache
def file_list(root):
    """The scan file list for root, computed once per verify run: the git
    file list when available, os.walk otherwise, filtered by skip rules.
    Callers clear the cache with file_list.cache_clear()."""
    rels = git_relpaths(root)
    if rels is not None:
        return [
            root / rel
            for rel in rels
            if rel
            and (root / rel).is_file()
            and not _skipped(Path(rel).parts[:-1])
        ]
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        dirnames[:] = [d for d in dirnames if not _skipped(rel.parts + (d,))]
        for name in filenames:
            if name != ".git":  # worktree marker is a file, not a dir
                files.append(Path(dirpath) / name)
    return files


def junk_file(name):
    """OS cruft and editor swap files excluded from tree comparisons."""
    return name in JUNK_NAMES or name.endswith(JUNK_SUFFIXES)


def _text_named(rel):
    """Whether rel names a file that must hold text: a known text
    suffix, or an extensionless entry point under scripts/."""
    return rel.suffix in TEXT_SUFFIXES or (
        rel.parts and rel.parts[0] == "scripts" and "." not in rel.name
    )


def read_text(path, rel):
    """File text, or None for binary or unreadable files. Files holding
    text in a non-UTF-8 encoding raise UnicodeDecodeError so the calling
    check can FAIL with the path instead of skipping silently; a
    UTF-16/32 BOM marks text in any file, whatever its suffix. A
    text-named file (see _text_named) holding NUL bytes raises
    BinaryFileError for the same reason."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith(_UTF_BOMS):
        return data.decode("utf-8")
    if b"\0" in data:
        if _text_named(rel):
            raise BinaryFileError(rel)
        return None
    return data.decode("utf-8")


def texts(root, bad, skip):
    """Yield (rel, text) for every scanned file that skip(rel) accepts
    and that decodes as UTF-8 text. Unreadable and binary files yield
    nothing; a file that fails UTF-8 decoding, or that holds binary
    bytes under a text name, appends '{rel}: ...' to bad instead."""
    for p in file_list(root):
        rel = p.relative_to(root)
        if skip(rel):
            continue
        try:
            text = read_text(p, rel)
        except BinaryFileError:
            bad.append(f"{rel}: binary content in a text file")
            continue
        except UnicodeDecodeError:
            bad.append(f"{rel}: not valid UTF-8")
            continue
        if text is not None:
            yield rel, text


def tail(result, n=5):
    text = (result.stderr or "") + (result.stdout or "")
    return " | ".join(text.strip().splitlines()[-n:])


def join(items, n=8):
    shown = items[:n]
    if len(items) > n:
        shown.append(f"+{len(items) - n} more")
    return "; ".join(shown)
