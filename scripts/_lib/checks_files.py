"""Repo-file checks: bin/, instruction files, local paths, source size.

file-size measures source files: every scanned file whose suffix is
.py, .js, .ts or .sh, plus extensionless entry points under scripts/.
"""

import json
import re

from . import miniyaml
from .checks_scan import (
    file_list,
    is_internal_doc,
    is_vendor,
    join,
    string_values,
    texts,
)

MAX_SOURCE_LINES = 400

# Written so these lines cannot match themselves. POSIX home paths need
# a non-URL left edge unless they follow the file: scheme or a '-v'/'='
# mount-style flag; /home/<x> counts at whitespace or end of line too,
# and the root home counts like the user homes. Windows home paths
# match either slash direction, any case.
LOCAL_PATH = re.compile(
    r"(?<![/\w:])(?:/root/|/home/[\w.-]+(?=[/\s]|$))"
    r"|(?:(?<=-v)|(?<![/\w:]))(?:/Users/)"
    r"|file:///(?:Users|home)/"
    r"|~/[A-Za-z0-9_]"
    r"|(?i:[A-Za-z]:[/\\]Users[/\\])"
)

# Suffixes whose decoded string values get the same local-path scan, so
# a JSON-escaped Windows home still counts.
DATA_SUFFIXES = {".json", ".yaml", ".yml"}

# Suffixes measured against MAX_SOURCE_LINES; extensionless files under
# scripts/ count too.
SOURCE_SUFFIXES = {".py", ".js", ".ts", ".sh"}


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


def _decoded_strings(rel, text):
    """String values inside a parsed .json/.yaml/.yml file. Unparseable
    files yield nothing: parse failures are prose-rules' business."""
    try:
        data = json.loads(text) if rel.suffix == ".json" else miniyaml.load(text)
    except Exception:
        return ()
    return string_values(data)


def check_no_local_paths(root):
    def skip(rel):
        return is_internal_doc(rel) or is_vendor(rel)

    bad = []
    for rel, text in texts(root, bad, skip):
        for i, line in enumerate(text.splitlines(), 1):
            if LOCAL_PATH.search(line):
                bad.append(f"{rel}:{i}")
        if rel.suffix in DATA_SUFFIXES and any(
            LOCAL_PATH.search(s) for s in _decoded_strings(rel, text)
        ):
            bad.append(f"{rel}: string value")
    return ("FAIL", join(bad)) if bad else ("PASS", "")


def check_file_size(root):
    def skip(rel):
        scripts_file = rel.parts and rel.parts[0] == "scripts" and "." not in rel.name
        return is_vendor(rel) or (
            rel.suffix not in SOURCE_SUFFIXES and not scripts_file
        )

    bad = []
    for rel, text in texts(root, bad, skip):
        n = len(text.splitlines())
        if n > MAX_SOURCE_LINES:
            bad.append(f"{rel} ({n} lines > {MAX_SOURCE_LINES})")
    return ("FAIL", join(bad)) if bad else ("PASS", "")
