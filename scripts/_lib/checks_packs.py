"""Pack schema check: every skills/betterterms-*/pack.yaml matches the
declared shape from the plan.

Keys exactly: name, command, mode, direction, triggers, intake,
discovery, research, savings. `name` is the pack's short slug and must
equal the folder suffix after `betterterms-`; `command` is the slug the
build turns into commands/<command>.md and must be unique across packs.
SKIP when no pack.yaml exists yet.
"""

import re

from . import miniyaml
from .checks_scan import display, file_list, join

REQUIRED_KEYS = {
    "name", "command", "mode", "direction", "triggers",
    "intake", "discovery", "research", "savings",
}
MODES = {"act", "coach", "both"}
DIRECTIONS = {"pay", "receive"}
RESEARCH_KINDS = {"policy", "pricing", "precedent", "rights", "market"}
DISCOVERY_KEYS = {"source", "find", "window_days"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PREFIX = "betterterms-"


def _pack_yamls(root):
    """(path, rel) for each skills/betterterms-*/pack.yaml. A symlinked
    pack.yaml is skipped: no-symlinks names the link itself."""
    for p in file_list(root):
        rel = p.relative_to(root)
        if (
            len(rel.parts) == 3
            and rel.parts[0] == "skills"
            and rel.parts[1].startswith(PREFIX)
            and rel.name == "pack.yaml"
            and not p.is_symlink()
        ):
            yield p, rel


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_list_of_strings(label, key, values, problems):
    if not isinstance(values, list) or not values:
        problems.append(f"{label}: {key}: must be a non-empty list")
        return
    if any(not isinstance(s, str) or not s.strip() for s in values):
        problems.append(f"{label}: {key}: entries must be non-empty strings")


def _check_discovery(label, items, problems):
    if not isinstance(items, list):
        problems.append(f"{label}: discovery: must be a list")
        return
    for i, item in enumerate(items, 1):
        entry = f"{label}: discovery[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{entry}: must be a mapping")
            continue
        if set(item) != DISCOVERY_KEYS:
            problems.append(f"{entry}: keys must be {sorted(DISCOVERY_KEYS)}")
            continue
        for k in ("source", "find"):
            if not isinstance(item[k], str) or not item[k].strip():
                problems.append(f"{entry}.{k}: must be a non-empty string")
        if not _is_int(item["window_days"]) or item["window_days"] <= 0:
            problems.append(f"{entry}.window_days: must be a positive integer")


def _check_research(label, items, problems):
    if not isinstance(items, list):
        problems.append(f"{label}: research: must be a list")
        return
    for i, item in enumerate(items, 1):
        entry = f"{label}: research[{i}]"
        if not isinstance(item, dict) or set(item) != {"kind"}:
            problems.append(f"{entry}: must be a mapping with key 'kind'")
            continue
        if item["kind"] not in RESEARCH_KINDS:
            problems.append(
                f"{entry}.kind: {item['kind']!r} "
                f"not in {sorted(RESEARCH_KINDS)}"
            )


def _check_pack(rel, folder, data, problems):
    label = display(rel)
    if not isinstance(data, dict):
        problems.append(f"{label}: must be a mapping")
        return
    extra = sorted(set(data) - REQUIRED_KEYS)
    missing = sorted(REQUIRED_KEYS - set(data))
    if extra:
        problems.append(f"{label}: unexpected keys: {', '.join(map(str, extra))}")
    if missing:
        problems.append(f"{label}: missing keys: {', '.join(missing)}")
        return
    name = data["name"]
    suffix = folder[len(PREFIX):]
    if not isinstance(name, str) or not SLUG.fullmatch(name):
        problems.append(f"{label}: name must be a slug, got {name!r}")
    elif name != suffix:
        problems.append(f"{label}: name {name!r} != folder suffix {suffix!r}")
    command = data["command"]
    if not isinstance(command, str) or not SLUG.fullmatch(command):
        problems.append(f"{label}: command must be a slug, got {command!r}")
    if data["mode"] not in MODES:
        problems.append(f"{label}: mode must be one of {sorted(MODES)}")
    if data["direction"] not in DIRECTIONS:
        problems.append(f"{label}: direction must be one of {sorted(DIRECTIONS)}")
    for key in ("triggers", "intake"):
        _check_list_of_strings(label, key, data[key], problems)
    _check_discovery(label, data["discovery"], problems)
    _check_research(label, data["research"], problems)
    savings = data["savings"]
    if (
        not isinstance(savings, dict)
        or set(savings) != {"formula"}
        or not isinstance(savings.get("formula"), str)
        or not savings["formula"].strip()
    ):
        problems.append(f"{label}: savings must map 'formula' to a string")


def check_pack_schema(root):
    problems = []
    commands = {}
    found = False
    for p, rel in _pack_yamls(root):
        found = True
        try:
            data = miniyaml.load(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, miniyaml.Error) as e:
            problems.append(f"{display(rel)}: cannot parse ({e})")
            continue
        _check_pack(rel, rel.parts[1], data, problems)
        if isinstance(data, dict) and isinstance(data.get("command"), str):
            other = commands.get(data["command"])
            if other is not None:
                problems.append(
                    f"{display(rel)}: command {data['command']!r} "
                    f"also used by {display(other)}"
                )
            else:
                commands[data["command"]] = rel
    if not found:
        return "SKIP", "no skills/betterterms-*/pack.yaml"
    return ("FAIL", join(problems)) if problems else ("PASS", "")
