"""Codex plugin and marketplace manifest generator.

gen(root, version) -> {relpath: content} produces the Codex view of
the kit: .codex-plugin/plugin.json (version lives here) and
.agents/plugins/marketplace.json (no version field, matching the
marketplace shape other plugin repos ship).
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
    short = kit["description"].split(":", 1)[0].strip()
    files = {
        ".codex-plugin/plugin.json": _dumps({
            "name": kit["name"],
            "version": version,
            "description": kit["description"],
            "author": kit["author"],
            "homepage": kit["repository"],
            "repository": kit["repository"],
            "license": kit["license"],
            "keywords": kit["keywords"],
            "skills": "./skills/",
            "interface": {
                "displayName": kit["name"],
                "shortDescription": short,
                "longDescription": kit["description"],
                "developerName": kit["author"]["name"],
                "category": "Developer Tools",
                "capabilities": ["Read", "Write"],
                "defaultPrompt": [
                    "Help me lower a bill.",
                    "Coach me through a salary negotiation.",
                ],
                "websiteURL": kit["repository"],
                "brandColor": "#0F766E",
                "screenshots": [],
            },
        }),
        ".agents/plugins/marketplace.json": _dumps({
            "name": kit["name"],
            "interface": {"displayName": kit["name"]},
            "plugins": [{
                "name": kit["name"],
                "source": {"source": "url", "url": "./"},
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Developer Tools",
            }],
        }),
    }
    return files
