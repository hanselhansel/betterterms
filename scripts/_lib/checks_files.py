"""Repo-file checks: bin/, instruction files, local paths, source size."""

import re

from .checks_scan import (
    file_list,
    is_internal_doc,
    is_vendor,
    join,
    texts,
)

MAX_SOURCE_LINES = 400

# Written so these lines cannot match themselves. POSIX home paths need
# a non-URL left edge unless they follow the file: scheme, and /home/<x>
# counts at end of line too; Windows home paths match either slash
# direction, any case.
LOCAL_PATH = re.compile(
    r"(?<![/\w:])(?:/Users/|/home/[\w.-]+(?:/|$))"
    r"|file:///(?:Users|home)/"
    r"|~/[A-Za-z0-9_]"
    r"|(?i:[A-Za-z]:[/\\]Users[/\\])"
)


def check_no_bin(root):
    if (root / "bin").exists():
        return "FAIL", "top-level bin/ is not allowed"
    return "PASS", ""


def check_no_root_claude_md(root):
    bad = [
        str(p.relative_to(root))
        for p in file_list(root)
        if p.name.lower() in ("claude.md", "agents.md")
    ]
    return ("FAIL", join(bad)) if bad else ("PASS", "")


def check_no_local_paths(root):
    def skip(rel):
        return is_internal_doc(rel) or is_vendor(rel)

    bad = []
    for rel, text in texts(root, bad, skip):
        for i, line in enumerate(text.splitlines(), 1):
            if LOCAL_PATH.search(line):
                bad.append(f"{rel}:{i}")
    return ("FAIL", join(bad)) if bad else ("PASS", "")


def check_file_size(root):
    def skip(rel):
        scripts_file = rel.parts and rel.parts[0] == "scripts" and "." not in rel.name
        return is_vendor(rel) or (rel.suffix not in (".py", ".js") and not scripts_file)

    bad = []
    for rel, text in texts(root, bad, skip):
        n = len(text.splitlines())
        if n > MAX_SOURCE_LINES:
            bad.append(f"{rel} ({n} lines > {MAX_SOURCE_LINES})")
    return ("FAIL", join(bad)) if bad else ("PASS", "")
