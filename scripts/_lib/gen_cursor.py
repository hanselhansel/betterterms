"""Cursor plugin manifest generator.

gen(root, version) -> {relpath: content} produces the Cursor view of
the kit: .cursor-plugin/plugin.json, modeled on the manifest
superpowers ships for Cursor (name, displayName, description,
version, author, homepage, repository, license, keywords, skills).
No hooks key: the repo's hooks/hooks.json is Claude Code schema, so
pointing Cursor at it would ship an unreadable hooks config.
"""

import json


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
    return {
        ".cursor-plugin/plugin.json": _dumps({
            "name": kit["name"],
            "displayName": kit["name"],
            "description": kit["description"],
            "version": version,
            "author": kit["author"],
            "homepage": kit["repository"],
            "repository": kit["repository"],
            "license": kit["license"],
            "keywords": kit["keywords"],
            "skills": "./skills/",
        }),
    }
