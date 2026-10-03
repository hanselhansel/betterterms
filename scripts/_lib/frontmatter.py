"""Read SKILL.md-style frontmatter: a YAML block between ``---`` lines at
the top of a file. Uses :mod:`miniyaml`, not PyYAML."""

from __future__ import annotations

from pathlib import Path

from . import miniyaml

_BLOCK_STYLES = ("|", ">", "|-", "|+", ">-", ">+")
# Characters a plain scalar may never start with in strict YAML. ``- ? :``
# count only when followed by a space or the end of the value.
_PLAIN_BAD_START = ",]#}&*!|>%@`"


class Error(Exception):
    """Raised when a file opens with ``---`` but never closes it, when
    the block is not a mapping, or when a value needs quoting for strict
    YAML compatibility."""


def parse(path):
    """Return (frontmatter_dict, body_str). A file that does not open with
    ``---`` yields ({}, full text)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text
    for j in range(1, len(lines)):
        if lines[j].rstrip() == "---":
            _check_values(path, lines[1:j])
            try:
                fm = miniyaml.load("\n".join(lines[1:j]))
            except miniyaml.Error as e:
                raise Error(f"{path}: {e}") from e
            if fm is None:
                fm = {}
            if not isinstance(fm, dict):
                raise Error(f"{path}: frontmatter is not a mapping")
            return fm, "\n".join(lines[j + 1:])
    raise Error(f"{path}: missing closing '---' in frontmatter")


def _check_values(path, fm_lines):
    """Reject ``key:`` values miniyaml accepts but strict YAML reads
    differently: a plain (unquoted) value containing ``': '`` or starting
    with an indicator character. Lines inside a ``|``/``>`` block scalar
    are content, not keys, and are skipped."""
    block_indent = None
    for i, line in enumerate(fm_lines, 2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if block_indent is not None and indent > block_indent:
            continue
        block_indent = None
        kv = miniyaml._split_key(line)
        if kv is None:
            continue
        v = kv[1].strip()
        if v in _BLOCK_STYLES:
            block_indent = indent
            continue
        if not v or v[0] in "\"'[{":
            continue
        if (
            v[0] in _PLAIN_BAD_START
            or (v[0] in "-?:" and (len(v) == 1 or v[1] == " "))
            or ": " in v
        ):
            raise Error(f"{path}: line {i}: frontmatter value {v!r} needs quoting")
