"""YAML frontmatter reader for SKILL.md files.

parse() splits the opening ``---`` block from the body and runs it
through :mod:`miniyaml` (a wrapper over vendored PyYAML), then applies
the frontmatter rules: the block must resolve to a mapping. The closing
fence counts only at column 0, and parse errors name the file line, one
past the parser's block line.
"""

from pathlib import Path

from . import miniyaml

Error = miniyaml.Error


def _scan(path):
    """Split the file at its frontmatter fences.

    Returns (block_lines, body): block_lines is None when the file has
    no ``---`` opener, body is None when the closing fence is missing.
    """
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---\n"):
        return None, text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    return lines[1:], None


def parse(path):
    """Return (frontmatter_dict, body). A file without a frontmatter block
    parses as ({}, whole text)."""
    block_lines, body = _scan(path)
    if block_lines is None:
        return {}, body
    if body is None:
        raise Error(f"{path}: unterminated frontmatter")
    if not body:
        raise Error(f"{path}: file ends at frontmatter")
    # Every block line was newline-terminated in the file; keep that edge.
    fm_text = "\n".join(block_lines) + "\n"
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
