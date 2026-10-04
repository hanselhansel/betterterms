"""Agent Plugins 1.0.0 root manifest generator.

gen(root, version) -> {relpath: content} produces plugin.json at the
repo root, the portable manifest that Agent Plugins clients (Codex,
Cursor, Copilot, VS Code, Kiro) read. The manifest schema is closed:
only $schema, name, version, description, author, homepage,
repository, license, keywords, and extensions are permitted. The
skills key names the skills/ tree the README promises; clients also
discover it by convention.
"""

import json

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def _dumps(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _kit(root):
    return json.loads((root / "kit.config.json").read_text(encoding="utf-8"))


def gen(root, version):
    # A root without skills/ is not the kit (partial checkout, script
    # test fixture); there is nothing to package, so emit nothing.
    if not (root / "skills").is_dir():
        return {}
    kit = _kit(root)
    author = {
        k: v for k, v in kit["author"].items()
        if k in ("name", "email", "url")
    }
    return {
        "plugin.json": _dumps({
            "$schema": SCHEMA,
            "name": kit["name"],
            "version": version,
            "description": kit["description"],
            "author": author,
            "homepage": kit["repository"],
            "repository": kit["repository"],
            "license": kit["license"],
            "keywords": kit["keywords"],
            "skills": "./skills/",
        }),
    }
