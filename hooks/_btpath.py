"""Locate bt.py for the settings hooks.

``CLAUDE_PLUGIN_ROOT`` points at the installed plugin root; the
runtime lives at ``skills/betterterms-guardrails/scripts/bt.py`` under
it. In a plain repo checkout the same relative path works, so the
hooks also run uninstalled and in tests.
"""

import os
import sys
from pathlib import Path


def plugin_root():
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent


def scripts_dir():
    return (
        plugin_root() / "skills" / "betterterms-guardrails" / "scripts"
    )


def bt_path():
    return scripts_dir() / "bt.py"


def import_btlib():
    """Put the runtime's script dir on sys.path so ``btlib`` imports.
    Returns the path added (already present is fine)."""
    d = str(scripts_dir())
    if d not in sys.path:
        sys.path.insert(0, d)
    return d
