#!/usr/bin/env python3
"""PreToolUse guard (spec 6.8), best effort.

Scoped to the betterterms data folder (``$BETTERTERMS_HOME``, default
``~/.betterterms``). Only path-bearing input fields are scanned --
``file_path``, ``path``, ``notebook_path``, the ``pattern``/``glob``
selectors and the Bash ``command``/``argv`` -- never free-text fields
like ``content``, ``prompt`` or ``description``, and no shell syntax
is parsed: the raw text itself decides.

A file path under the home passes only for reads of the skills' own
case files (``brief.yaml``, ``plan.yaml``, ``draft.yaml``,
``inbound.yaml``, ``gate.json``, ``thread.md``, ``sources/*``) and of
user drops in ``cases/<id>/inbox/``, and for writes to the files the
agent owns (``draft.yaml``, ``inbound.yaml``, ``thread.md``,
``sources/*``). ``gate.json`` is read-only: ``bt.py gate`` writes it.
``.floor``, ``held/``, ``ledger.jsonl`` and ``config.yaml`` are
private to bt.py at any depth, and everything else under the home is
denied. The session transcript's own ``*.jsonl`` files are denied;
the folder itself and ``memory/`` under it are not. Outside the home
nothing applies, so an unrelated project's ``held/`` or ``.floor``
file is untouched.

A command that names the home in any spelling (its absolute path,
``~/.betterterms``, ``$BETTERTERMS_HOME``, the ``.betterterms``
basename) or any of ``held``, ``.floor``, ``set-floor``, ``bt.py`` is
allowed only as one whole raw
``python3 <.../betterterms-guardrails/scripts/bt.py> <args>`` call
whose characters stay inside [A-Za-z0-9._/=:@+,-] and single spaces.
``held approve``, ``held reject`` and ``case set-floor`` are user
actions and deny even inside the strict shape; variables, globs,
quotes, separators, newlines, ``$(``, backticks, ``cd``, pipes and
redirects are all outside the shape, so they deny.

The guard is best effort: outside the mod the agent runs as the
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

# Path-bearing tool_input fields. Free-text fields are never scanned.
_PATH_KEYS = ("file_path", "path", "notebook_path")
_SELECTOR_KEYS = ("pattern", "glob")
_COMMAND_KEYS = ("command", "argv")
_FREE_KEYS = {
    "content", "new_string", "old_string", "description", "prompt",
}

# Tools that only read; any other tool touching a path under the home
# is judged by the write allowlist.
_READ_TOOLS = {"Read", "Glob", "Grep", "LS"}

# The names inside a case folder. gate.json is verdict output: reads
# are fine, writes belong to bt.py gate alone. ``inbox/`` holds user
# drops: the agent reads them, never writes them.
_READ_FILES = {
    "brief.yaml", "plan.yaml", "draft.yaml", "inbound.yaml",
    "gate.json", "thread.md",
}
_READ_DIRS = {"sources", "inbox"}
_WRITE_FILES = {"draft.yaml", "inbound.yaml", "thread.md"}
_WRITE_DIRS = {"sources"}

# Under the home these never pass in a path field, at any depth.
_PRIVATE_NAMES = {"held", ".floor", "ledger.jsonl", "config.yaml"}

# A command naming the home in any spelling, or any of these names,
# is allowed only as the strict bt.py shape below.
_MARKERS = (
    "held", ".floor", "set-floor", "bt.py", ".betterterms",
    "$betterterms_home", "${betterterms_home}",
)

_SAFE = r"[A-Za-z0-9._/=:@+,-]"
_BT_CALL = re.compile(rf"python3 {_SAFE}+( {_SAFE}+)*")
_BT_SUFFIX = "/betterterms-guardrails/scripts/bt.py"
_USER_ONLY = {
    ("held", "approve"), ("held", "reject"), ("case", "set-floor"),
}


def _resolve(text, cwd, home):
    """Resolve a path-field value: our env vars and ``~`` expand,
    relative values join the call's cwd, and ``..``/``.`` segments
    normalize out."""
    t = text
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


def _fields(tool_input, cwd, tool):
    """``(kind, value, read_only)`` for each path-bearing field, with
    selectors joined onto their sibling ``path`` when one sits beside
    them. Everything else -- free text above all -- is skipped."""
    stack = [tool_input]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            base = value.get("path")
            base = base if isinstance(base, str) else cwd
            for k, v in value.items():
                if k in _FREE_KEYS:
                    continue
                if k in _SELECTOR_KEYS and isinstance(v, str):
                    joined = v if v.startswith(("/", "~", "$")) \
                        else f"{base.rstrip('/')}/{v}"
                    yield "path", joined, True
                elif k in _PATH_KEYS and isinstance(v, str):
                    yield "path", v, tool in _READ_TOOLS
                elif k in _COMMAND_KEYS and isinstance(v, str):
                    yield "cmd", v, False
                elif (
                    k in _COMMAND_KEYS
                    and isinstance(v, list)
                    and all(isinstance(x, str) for x in v)
                ):
                    yield "cmd", " ".join(v), False
                else:
                    stack.append(v)
        elif isinstance(value, list):
            stack.extend(value)


def _check_command(raw, homes, tdir):
    """A deny reason for a command string, or None. The raw text is
    matched as-is: no quoting, expansion or separator parsing."""
    if tdir is not None and tdir in raw and ".jsonl" in raw:
        return "betterterms: the session log is off limits"
    low = raw.lower()
    if not any(m in low for m in _MARKERS) and not any(
        h.lower() in low for h in homes
    ):
        return None
    deny = (
        "betterterms: a command naming the betterterms home, held/, "
        ".floor, set-floor or bt.py passes only as one plain "
        "`python3 <.../betterterms-guardrails/scripts/bt.py> <args>` call"
    )
    if _BT_CALL.fullmatch(raw) is None:
        return deny
    tokens = raw.split(" ")
    if not tokens[1].endswith(_BT_SUFFIX):
        return deny
    args = tokens[2:]
    if tuple(args[:2]) in _USER_ONLY or any(
        "set-floor" in a for a in args
    ):
        return (
            "betterterms: held approve, held reject and "
            "case set-floor run only from a user action"
        )
    return None


def _check_path(text, cwd, home, homes, tdir, transcript, read_only):
    """A deny reason for a resolved path field, or None."""
    resolved = _resolve(text, cwd, home)
    if _is_transcript(resolved, tdir, transcript):
        return "betterterms: the session log is off limits"
    rel = None
    for h in homes:
        if resolved == h:
            rel = ""
            break
        if resolved.startswith(h + "/"):
            rel = resolved[len(h) + 1:]
            break
    if rel is None:
        return None
    parts = rel.split("/")
    if any(p in _PRIVATE_NAMES for p in parts):
        return (
            "betterterms: .floor, held/ records, ledger.jsonl and "
            "config.yaml are private to bt.py"
        )
    ok = False
    if (
        len(parts) >= 3
        and parts[0] == "cases"
        and _CASE_ID.fullmatch(parts[1])
    ):
        inner = parts[2:]
        if read_only:
            ok = (len(inner) == 1 and inner[0] in _READ_FILES) or \
                inner[0] in _READ_DIRS
        else:
            ok = (len(inner) == 1 and inner[0] in _WRITE_FILES) or (
                inner[0] in _WRITE_DIRS and len(inner) >= 2
            )
    if ok:
        return None
    if read_only:
        return (
            "betterterms: reads under the home reach only the case "
            "files and cases/<id>/inbox/ drops"
        )
    return (
        "betterterms: writes under the home land only on draft.yaml, "
        "inbound.yaml, thread.md and sources/"
    )


def _is_transcript(resolved, tdir, transcript):
    if transcript is not None and resolved == transcript:
        return True
    if tdir is None or not resolved.startswith(tdir + "/"):
        return False
    rel = resolved[len(tdir) + 1:]
    return "/" not in rel and rel.endswith(".jsonl")


def _transcript_dir(event):
    raw = event.get("transcript_path")
    if not isinstance(raw, str) or not raw:
        return None, None
    path = os.path.normpath(raw)
    parent = str(Path(path).parent)
    if len(Path(parent).parts) < 3:
        return None, path
    return parent, path


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
    return base, [base] + ([real] if real != base else [])


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict):
        return 0
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    cwd = str(event.get("cwd") or "/")
    tool = event.get("tool_name")
    tool = tool if isinstance(tool, str) else ""
    home, homes = _homes()
    tdir, transcript = _transcript_dir(event)
    for kind, value, read_only in _fields(tool_input, cwd, tool):
        if kind == "cmd":
            reason = _check_command(value, homes, tdir)
        else:
            reason = _check_path(
                value, cwd, home, homes, tdir, transcript, read_only
            )
        if reason is not None:
            _deny(reason)
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
