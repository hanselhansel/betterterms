"""Skill folder and SKILL.md frontmatter rules."""

import re

from . import frontmatter
from .checks_scan import file_list, join

# Name segments are lowercase alnum joined by single hyphens: no leading,
# trailing or double hyphens; 1-64 chars total.
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX = 64
ALLOWED_FM_KEYS = {"name", "description", "license",
                   "compatibility", "metadata", "allowed-tools"}
MAX_SKILL_BODY_LINES = 500
MAX_DESCRIPTION_CHARS = 1024
MAX_COMPATIBILITY_CHARS = 500


def _skill_names(root):
    """Skill folder names from the shared file list: every directory
    directly under skills/ that holds at least one scanned file."""
    skills = root / "skills"
    if not skills.is_dir():
        return None
    names = set()
    for p in file_list(root):
        parts = p.relative_to(root).parts
        if len(parts) > 2 and parts[0] == "skills":
            names.add(parts[1])
    return sorted(names)


def _check_optional_fields(name, fm, problems):
    """Type rules for frontmatter keys that may be present."""
    if "license" in fm and not isinstance(fm["license"], str):
        problems.append(f"skills/{name}: license must be a string")
    compat = fm.get("compatibility")
    if compat is not None and (
        not isinstance(compat, str) or len(compat) > MAX_COMPATIBILITY_CHARS
    ):
        problems.append(
            f"skills/{name}: compatibility must be a string "
            f"<= {MAX_COMPATIBILITY_CHARS} chars"
        )
    meta = fm.get("metadata")
    if meta is not None and (
        not isinstance(meta, dict)
        or any(
            not isinstance(k, str) or not isinstance(v, str)
            for k, v in meta.items()
        )
    ):
        problems.append(f"skills/{name}: metadata must map strings to strings")
    tools = fm.get("allowed-tools")
    if tools is not None and not (
        isinstance(tools, str)
        or (isinstance(tools, list) and all(isinstance(t, str) for t in tools))
    ):
        problems.append(
            f"skills/{name}: allowed-tools must be a string or list of strings"
        )


def check_skill_names(root):
    names = _skill_names(root)
    if names is None:
        return "SKIP", "no skills/ directory"
    problems = []
    for name in names:
        if (
            not SKILL_NAME.match(name)
            or len(name) > SKILL_NAME_MAX
            or not name.startswith("betterterms-")
        ):
            problems.append(f"skills/{name}: folder must be betterterms-[a-z0-9-]")
        skill_md = root / "skills" / name / "SKILL.md"
        if not skill_md.is_file():
            problems.append(f"skills/{name}: missing SKILL.md")
            continue
        try:
            fm, body = frontmatter.parse(skill_md)
        except Exception as e:
            problems.append(f"skills/{name}: {e}")
            continue
        extra = sorted(str(k) for k in fm if k not in ALLOWED_FM_KEYS)
        if extra:
            problems.append(f"skills/{name}: unexpected keys: {', '.join(extra)}")
        if fm.get("name") != name:
            problems.append(f"skills/{name}: name {fm.get('name')!r} != folder")
        desc = fm.get("description")
        if not isinstance(desc, str) or not desc.strip():
            problems.append(f"skills/{name}: missing description")
        elif len(desc) > MAX_DESCRIPTION_CHARS:
            problems.append(f"skills/{name}: description {len(desc)} chars > {MAX_DESCRIPTION_CHARS}")
        _check_optional_fields(name, fm, problems)
        body_lines = len(body.splitlines())
        if body_lines > MAX_SKILL_BODY_LINES:
            problems.append(f"skills/{name}: body {body_lines} lines > {MAX_SKILL_BODY_LINES}")
    return ("FAIL", join(problems)) if problems else ("PASS", "")
