"""Skill folder and SKILL.md frontmatter rules."""

import re

from . import frontmatter
from .checks_scan import join

# Name segments are lowercase alnum joined by single hyphens: no leading,
# trailing or double hyphens; 1-64 chars total.
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX = 64
ALLOWED_FM_KEYS = {"name", "description", "license",
                   "compatibility", "metadata", "allowed-tools"}
MAX_SKILL_BODY_LINES = 500
MAX_DESCRIPTION_CHARS = 1024


def check_skill_names(root):
    skills = root / "skills"
    if not skills.is_dir():
        return "SKIP", "no skills/ directory"
    problems = []
    for folder in sorted(skills.iterdir()):
        if not folder.is_dir():
            continue
        name = folder.name
        if (
            not SKILL_NAME.match(name)
            or len(name) > SKILL_NAME_MAX
            or not name.startswith("betterterms-")
        ):
            problems.append(f"skills/{name}: folder must be betterterms-[a-z0-9-]")
        skill_md = folder / "SKILL.md"
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
        body_lines = len(body.splitlines())
        if body_lines > MAX_SKILL_BODY_LINES:
            problems.append(f"skills/{name}: body {body_lines} lines > {MAX_SKILL_BODY_LINES}")
    return ("FAIL", join(problems)) if problems else ("PASS", "")
