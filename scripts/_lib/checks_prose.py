"""Prose rules for shipped markdown and JSON/YAML string values."""

import json
import re

from . import miniyaml
from .checks_scan import (
    file_list,
    is_internal_doc,
    is_vendor,
    join,
    texts,
)

# "leverag\w*" bans every form of "leverage": the noun as well as the
# verb, because this rule cannot tell parts of speech apart.
BANNED_WORDS = re.compile(
    r"\b(delv\w*|pivotal|crucial|showcas\w*|leverag\w*|robust|comprehensive|"
    r"nuanced|underscor\w*|foster\w*|moreover|furthermore)\b",
    re.IGNORECASE,
)
EM_DASH = "—"


def _prose_hit(label, text, bad):
    if EM_DASH in text:
        bad.append(f"{label}: em dash")
    m = BANNED_WORDS.search(text)
    if m:
        bad.append(f"{label}: banned word {m.group(0)!r}")


def _strings(value):
    """Every string value inside a parsed JSON/YAML structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, (dict, list)):
        for v in (value.values() if isinstance(value, dict) else value):
            yield from _strings(v)


def _data_files(root):
    """kit.config.json plus skills/**/*.{json,yaml,yml}, vendor exempt."""
    for p in file_list(root):
        rel = p.relative_to(root)
        in_skills = rel.parts[0] == "skills" and p.suffix in (".json", ".yaml", ".yml")
        if not is_vendor(rel) and (in_skills or rel.parts == ("kit.config.json",)):
            yield p, rel


def check_prose_rules(root):
    def skip(rel):
        return rel.suffix != ".md" or is_internal_doc(rel) or is_vendor(rel)

    bad = []
    for rel, text in texts(root, bad, skip):
        for i, line in enumerate(text.splitlines(), 1):
            _prose_hit(f"{rel}:{i}", line, bad)
    for p, rel in _data_files(root):
        try:
            text = p.read_text(encoding="utf-8")
            data = json.loads(text) if p.suffix == ".json" else miniyaml.load(text)
        except (OSError, UnicodeDecodeError, ValueError, miniyaml.Error) as e:
            bad.append(f"{rel}: cannot parse ({e})")
            continue
        for s in _strings(data):
            _prose_hit(f"{rel}: string value", s, bad)
    return ("FAIL", join(bad)) if bad else ("PASS", "")
