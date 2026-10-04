#!/usr/bin/env python3
"""PreToolUse guard (spec 6.8), best effort.

Scoped to the betterterms data folder (``$BETTERTERMS_HOME``, default
``~/.betterterms``). A tool call whose input names a path under that
home is denied, with two exceptions: the case files the skills write
themselves (``brief.yaml``, ``plan.yaml``, ``draft.yaml``,
``inbound.yaml``, ``gate.json``, ``thread.md``, ``sources/*``), and a
Bash command that is one whole ``bt.py`` invocation. ``.floor``,
``held/``, ``ledger.jsonl`` and ``config.yaml`` stay denied either
way, and ``held approve``, ``held reject`` and ``case set-floor``
spelled as bt.py commands are denied outright: those are user
actions, not agent ones. The session transcript's own ``*.jsonl``
files are denied; the folder itself and ``memory/`` under it are
not. Outside the home nothing applies, so an unrelated project's
``held/`` or ``.floor`` is untouched.

Text is normalized before matching: quotes, backslashes and
``$IFS``-style splits collapse, ``~`` and ``$HOME``-style variables
expand, and ``..`` segments resolve, so a disguised path cannot slip
past. The guard is best effort: outside the mod the agent runs as the
user, so a determined one can still reach the data; only the mod's
in-memory approval resists that. Input the guard cannot parse lets
the call through: a broken guard must not wedge every tool call.
"""

import json
import os
import re
import sys
from pathlib import Path

_CASE_ID = re.compile(r"[a-z0-9-]+")

# Commands only a user action may run; anywhere they appear, deny.
_USER_ONLY = re.compile(
    r"\bbt(?:\.py)?\s+(?:held\s+(?:approve|reject)|case\s+set-floor)\b",
    re.I,
)

# A command that is only a bt.py call: optional VAR=value prefixes and
# a python launcher, the bt.py path, then arguments -- but no shell
# chaining, piping or redirection.
_BT_WHOLE = re.compile(
    r"^\s*(?:\w+=\S+\s+)*(?:python[\d.]*\s+)?\S*?/?bt\.py"
    r"(?:\s+[^;&|<>]*)?\s*$",
    re.I,
)

_TOKENS = re.compile(r"[\s;|&<>=(){}]+")

# The names inside a case folder the agent reads and writes itself.
_CASE_FILES = {
    "brief.yaml",
    "plan.yaml",
    "draft.yaml",
    "inbound.yaml",
    "gate.json",
    "thread.md",
}

# Under the home these never pass, not even as a bt.py argument:
# the walk-away file, the held-draft records and approval markers,
# the savings ledger and the user config.
_PROTECTED_NAMES = {"ledger.jsonl", "config.yaml"}


def _normalize(text):
    """Collapse quoting tricks before matching: ``$IFS`` variants to
    spaces, quotes and backslashes away, whitespace runs to one."""
    t = re.sub(r"\$\{IFS[^}]*\}|\$IFS\b", " ", text)
    t = t.replace("\\", "").replace("'", "").replace('"', "")
    t = t.replace("`", "")
    return re.sub(r"\s+", " ", t)


def _strings(value):
    """Every string inside a tool_input structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        yield " ".join(str(v) for v in value)
        for v in value:
            yield from _strings(v)


def _expand(token, cwd, home):
    """Resolve ``token`` to an absolute path guess: our env vars and
    ``~`` expand, relative tokens join the call's cwd, and ``..`` and
    ``.`` segments normalize out."""
    t = token
    for var, val in (
        ("${BETTERTERMS_HOME}", home),
        ("$BETTERTERMS_HOME", home),
        ("${HOME}", str(Path.home())),
        ("$HOME", str(Path.home())),
    ):
        if t == var or t.startswith(var + "/"):
            t = val + t[len(var):]
            break
    if t.startswith("~"):
        t = os.path.expanduser(t)
    if not t.startswith("/"):
        t = f"{cwd}/{t}"
    return os.path.normpath(t)


def _classify(path, homes):
    """``protected`` / ``file`` / ``other`` for a path under the
    betterterms home, or None when it is outside every spelling."""
    for home in homes:
        if path == home:
            return "other"
        if not path.startswith(home + "/"):
            continue
        rel = path[len(home) + 1:]
        parts = rel.split("/")
        if "held" in parts or ".floor" in parts:
            return "protected"
        if rel in _PROTECTED_NAMES:
            return "protected"
        if (
            len(parts) >= 3
            and parts[0] == "cases"
            and _CASE_ID.fullmatch(parts[1])
            and (
                (len(parts) == 3 and parts[2] in _CASE_FILES)
                or (len(parts) == 4 and parts[2] == "sources")
            )
        ):
            return "file"
        return "other"
    return None


def _transcript(event):
    """``(dir, file)`` for the session transcript; the dir is only
    trusted when it is deep enough to be a real session location, and
    only direct ``*.jsonl`` children of it are off limits."""
    raw = event.get("transcript_path")
    if not isinstance(raw, str) or not raw:
        return None, None
    path = os.path.normpath(raw)
    parent = str(Path(path).parent)
    if len(Path(parent).parts) < 3:
        return None, path
    return parent, path


def _is_transcript(path, tdir, transcript):
    if transcript is not None and path == transcript:
        return True
    if tdir is None or not path.startswith(tdir + "/"):
        return False
    rel = path[len(tdir) + 1:]
    return "/" not in rel and rel.endswith(".jsonl")


def _pathish(token):
    """A token worth resolving as a path: separators, expansions or
    a dot mark it, or it is a bare ``held``/``cases`` name that only
    matters when the call already runs inside the home."""
    return (
        "/" in token
        or "." in token
        or token.startswith(("~", "$"))
        or token in ("held", "cases")
    )


def _check(text, cwd, homes, tdir, transcript):
    """A deny reason for one input string, or None."""
    norm = _normalize(text)
    if _USER_ONLY.search(norm):
        return (
            "betterterms: held approve, held reject and "
            "case set-floor run only from a user action"
        )
    whole_bt = _BT_WHOLE.fullmatch(norm) is not None
    names_home = False
    for tok in _TOKENS.split(norm):
        if not _pathish(tok):
            continue
        path = _expand(tok, cwd, homes[0])
        if _is_transcript(path, tdir, transcript):
            return "betterterms: the session log is off limits"
        cls = _classify(path, homes)
        if cls == "protected":
            return (
                "betterterms: .floor, held/ records, ledger.jsonl "
                "and config.yaml are private to bt.py"
            )
        if cls == "other":
            names_home = True
    if names_home and not whole_bt:
        return (
            "betterterms: files under the betterterms home are "
            "private to bt.py and the skills' own case files"
        )
    return None


def _deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _homes():
    raw = os.environ.get("BETTERTERMS_HOME") or "~/.betterterms"
    base = os.path.normpath(os.path.expanduser(raw))
    real = os.path.normpath(os.path.realpath(base))
    return [base] + ([real] if real != base else [])


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    homes = _homes()
    cwd = str(event.get("cwd") or "/")
    tdir, transcript = _transcript(event)
    for s in _strings(event.get("tool_input")):
        reason = _check(s, cwd, homes, tdir, transcript)
        if reason is not None:
            _deny(reason)
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
