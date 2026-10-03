"""YAML frontmatter reader for SKILL.md files.

parse() splits the opening ``---`` block from the body and runs it through
:mod:`miniyaml` (which defines and enforces the supported YAML subset) so
frontmatter never accepts syntax miniyaml would reject, then applies the
frontmatter rules: the block must resolve to a mapping.
"""

from pathlib import Path

from . import miniyaml

Error = miniyaml.Error


def block(path):
    """The newline-terminated frontmatter block text, or None when the
    file has no frontmatter."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---\n"):
        return None
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return "\n".join(lines[1:i]) + "\n"
    return None


def parse(path):
    """Return (frontmatter_dict, body). A file without a frontmatter block
    parses as ({}, whole text)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---\n"):
        return {}, text
    lines = text.split("\n")
    close = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            close = i
            break
    if close is None:
        raise Error(f"{path}: unterminated frontmatter")
    body = "\n".join(lines[close + 1:])
    if not body:
        raise Error(f"{path}: file ends at frontmatter")
    # Every block line was newline-terminated in the file; keep that edge.
    fm_text = "\n".join(lines[1:close]) + "\n"
    try:
        fm = miniyaml.load(fm_text)
    except miniyaml.Error as e:
        # The parser names the block line; the file line adds the opening
        # '---' line.
        raise Error(f"{path}: line {(e.line or 1) + 1}: {e.message}")
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        raise Error(f"{path}: frontmatter is not a mapping")
    return fm, body
