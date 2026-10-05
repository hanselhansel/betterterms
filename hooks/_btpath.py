"""Locate bt.py for the settings hooks.

``CLAUDE_PLUGIN_ROOT`` points at the installed plugin root; the
runtime lives at ``skills/betterterms-guardrails/scripts/bt.py``
under it. The same relative path works in a plain repo checkout, so
the hooks also run uninstalled and in tests. Vendored into a repo,
the hooks sit at ``.claude/betterterms/hooks`` beside the vendored
skills under ``.claude/skills``; ``CLAUDE_PROJECT_DIR`` names that
repo's root when the session exports it.
"""

import os
import sys
from pathlib import Path

_REL = ("skills", "betterterms-guardrails", "scripts")


def _candidates():
    """The dirs that may hold ``skills/betterterms-guardrails/scripts``
    when no plugin root is set, best anchor first: the checkout where
    this file lives (``hooks/`` at the root), the vendored layout
    (``.claude/betterterms/hooks/`` under the repo's ``.claude``), and
    the session's project dir."""
    here = Path(__file__).resolve()
    yield here.parents[1].joinpath(*_REL)
    yield here.parents[2].joinpath(*_REL)
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        yield (Path(project).expanduser() / ".claude").joinpath(*_REL)


def scripts_dir():
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).expanduser().joinpath(*_REL)
    candidates = list(_candidates())
    for d in candidates:
        if (d / "bt.py").is_file():
            return d
    return candidates[0]


def bt_path():
    return scripts_dir() / "bt.py"


def import_btlib():
    """Put the runtime's script dir on sys.path so ``btlib`` imports.
    Returns the path added (already present is fine)."""
    d = str(scripts_dir())
    if d not in sys.path:
        sys.path.insert(0, d)
    return d
