"""Read SKILL.md-style frontmatter: a YAML block between ``---`` lines at
the top of a file. Uses :mod:`miniyaml`, not PyYAML."""

from __future__ import annotations

from pathlib import Path

from . import miniyaml


class Error(Exception):
    """Raised when a file opens with ``---`` but never closes it, or when
    the block is not a mapping."""


def parse(path):
    """Return (frontmatter_dict, body_str). A file that does not open with
    ``---`` yields ({}, full text)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text
    for j in range(1, len(lines)):
        if lines[j].strip() == "---":
            fm = miniyaml.load("\n".join(lines[1:j]))
            if fm is None:
                fm = {}
            if not isinstance(fm, dict):
                raise Error(f"{path}: frontmatter is not a mapping")
            return fm, "\n".join(lines[j + 1:])
    raise Error(f"{path}: missing closing '---' in frontmatter")
