#!/usr/bin/env python3
"""PreToolUse guard (spec 6.8), best effort.

Denies any tool call whose input names a ``.floor`` file, a ``held/``
path, the ``held approve`` or ``case set-floor`` commands, or the
session transcript directory (``transcript_path``'s parent). The
walk-away and the approval path belong to the user; inbound text can
still never reach them because the gate and the prompt hook own the
writes. Input the guard cannot parse lets the call through: a broken
guard must not wedge every tool call.
"""

import json
import re
import sys
from pathlib import Path

_FLOOR = re.compile(r"(?:^|[^\w.])\.floor(?!\w)")
_HELD_DIR = re.compile(r"(?:^|[^\w])held(?:/|$)")
_HELD_APPROVE = re.compile(r"held\s+approve\b", re.I)
_SET_FLOOR = re.compile(r"case\s+set-floor\b", re.I)

_RULES = (
    (_FLOOR, "betterterms: .floor files are read only by bt.py"),
    (
        _HELD_DIR,
        "betterterms: held/ records are written only by user actions",
    ),
    (
        _HELD_APPROVE,
        "betterterms: held approve runs only from a user action",
    ),
    (
        _SET_FLOOR,
        "betterterms: case set-floor runs only from the user",
    ),
)


def _strings(value):
    """Every string inside a tool_input structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


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


def _names_dir(text, dirpath):
    """``dirpath`` appears in text at a path boundary: the char after
    it may deepen the path but may not extend the name."""
    return (
        re.search(re.escape(dirpath) + r"(?![\w.-])", text)
        is not None
    )


def _transcript_dir(event):
    """The session transcript directory, when the path is deep enough
    to be a real session log location and not a shared temp root."""
    raw = event.get("transcript_path")
    if not isinstance(raw, str) or not raw:
        return None
    parent = Path(raw).parent
    if len(parent.parts) < 3:
        return None
    return str(parent)


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    transcript_dir = _transcript_dir(event)
    for s in _strings(event.get("tool_input")):
        for rx, reason in _RULES:
            if rx.search(s):
                _deny(reason)
                return 0
        if transcript_dir and _names_dir(s, transcript_dir):
            _deny("betterterms: the session log is off limits")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
