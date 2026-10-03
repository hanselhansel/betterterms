"""Claude Code plugin and marketplace manifest generator.

gen(root, version) -> {relpath: content} produces the Claude view of
the kit: .claude-plugin/plugin.json (the only file that carries the
version), .claude-plugin/marketplace.json, commands/betterterms.md,
and commands/<command>.md for every skills/betterterms-*/pack.yaml
that declares a `command` key. With no packs installed the command
set is the entry point alone.
"""

import json
import re

from . import frontmatter, miniyaml

_COMMAND_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_ENTRY_DESCRIPTION = (
    "Start a betterterms negotiation. Routes bills, refunds, "
    "cancellations, subscriptions, and job offers to the right pack."
)


def _dumps(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _kit(root):
    return json.loads((root / "kit.config.json").read_text(encoding="utf-8"))


def _command_md(description, skill):
    return (
        f"---\ndescription: {description}\n---\n\n"
        f"Use the {skill} skill for this request. Pass the user's "
        "words through unchanged.\n"
    )


def _skill_description(folder):
    try:
        fm, _body = frontmatter.parse(folder / "SKILL.md")
    except Exception:
        return None
    desc = fm.get("description")
    return desc if isinstance(desc, str) and desc.strip() else None


def _pack_commands(root):
    """{(command, skill_name, description)} from each pack.yaml that
    declares `command`. A pack.yaml that fails to parse, or names a
    command that is not a safe single path segment, is a build error:
    silently skipping it would ship a missing entry point."""
    skills = root / "skills"
    out = []
    if not skills.is_dir():
        return out
    for folder in sorted(skills.iterdir()):
        pack = folder / "pack.yaml"
        if not folder.is_dir() or not pack.is_file():
            continue
        try:
            data = miniyaml.load(pack.read_text(encoding="utf-8"))
        except miniyaml.Error as e:
            raise ValueError(f"{pack}: {e}") from e
        if not isinstance(data, dict) or "command" not in data:
            continue
        command = data["command"]
        if not isinstance(command, str) or not _COMMAND_NAME.fullmatch(command):
            raise ValueError(f"{pack}: bad command name {command!r}")
        desc = _skill_description(folder) or f"betterterms pack {folder.name}."
        out.append((command, folder.name, desc))
    return out


def gen(root, version):
    # A root without skills/ is not the kit (partial checkout, script
    # test fixture); there is nothing to package, so emit nothing.
    if not (root / "skills").is_dir():
        return {}
    kit = _kit(root)
    files = {
        ".claude-plugin/plugin.json": _dumps({
            "name": kit["name"],
            "version": version,
            "description": kit["description"],
            "author": kit["author"],
            "repository": kit["repository"],
            "license": kit["license"],
            "keywords": kit["keywords"],
        }),
        ".claude-plugin/marketplace.json": _dumps({
            "name": kit["name"],
            "description": kit["description"],
            "owner": {"name": kit["author"]["name"]},
            "plugins": [{
                "name": kit["name"],
                "source": "./",
                "description": kit["description"],
            }],
        }),
        "commands/betterterms.md": _command_md(
            _ENTRY_DESCRIPTION, "betterterms-start"
        ),
    }
    for command, skill, desc in _pack_commands(root):
        files[f"commands/{command}.md"] = _command_md(desc, skill)
    return files
