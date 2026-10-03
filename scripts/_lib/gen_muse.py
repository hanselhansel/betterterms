"""Muse plugin manifest generator.

gen(root, version) -> {relpath: content} produces
.muse-plugin/plugin.json with schemaVersion 1. Meta does not document
the Muse manifest; this shape is modeled on the .muse-plugin/plugin.json
that superpowers 6.4.2 ships, and the assumption is recorded in
docs/decisions/0011-host-manifests.md. Skills are listed explicitly
under capabilities.skills as {id, path} pairs, one per
skills/<name>/SKILL.md. The session-start hook mirrors the one
superpowers registers; hooks/session-start.sh is plain sh and prints
the pointer to betterterms-start.
"""

import json


def _dumps(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _kit(root):
    return json.loads((root / "kit.config.json").read_text(encoding="utf-8"))


def _skills(root):
    out = []
    for folder in sorted((root / "skills").iterdir()):
        if folder.is_dir() and (folder / "SKILL.md").is_file():
            out.append({
                "id": folder.name,
                "path": f"skills/{folder.name}/SKILL.md",
            })
    return out


def gen(root, version):
    # A root without skills/ is not the kit (partial checkout, script
    # test fixture); there is nothing to package, so emit nothing.
    if not (root / "skills").is_dir():
        return {}
    kit = _kit(root)
    return {
        ".muse-plugin/plugin.json": _dumps({
            "schemaVersion": 1,
            "name": kit["name"],
            "displayName": kit["name"],
            "version": version,
            "description": kit["description"],
            "compat": {
                "source": "native",
                "manifestDir": ".muse-plugin",
            },
            "capabilities": {
                "skills": _skills(root),
                "commands": [],
                "hooks": [{
                    "id": "session-start",
                    "event": "SessionStart",
                    "command": ["sh", "hooks/session-start.sh"],
                    "timeoutMs": 5000,
                }],
                "mcpServers": [],
                "reminders": [],
            },
        }),
    }
