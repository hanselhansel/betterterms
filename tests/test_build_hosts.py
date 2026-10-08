import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from _lib import gen_agent_plugins  # noqa: E402
from _lib.checks_prose import BANNED_WORDS, EM_DASH  # noqa: E402
from test_build_gen import make_root  # noqa: E402

VERSION = (REPO / "VERSION").read_text(encoding="utf-8").strip()
KIT = json.loads((REPO / "kit.config.json").read_text(encoding="utf-8"))

GENERATORS = (gen_agent_plugins,)

# Agent Plugins 1.0.0: closed manifest schema, section 5.2. The skills
# key names the skills/ tree the README promises; clients also discover
# it from the fixed location.
AGENT_PLUGINS_SCHEMA = (
    "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
)
AGENT_PLUGINS_FIELDS = {
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions", "skills",
}
AGENT_PLUGINS_NAME = re.compile(r"[a-z0-9][a-z0-9.-]*[a-z0-9]|[a-z0-9]")


def generated(root, version=VERSION):
    out = {}
    for mod in GENERATORS:
        out.update(mod.gen(root, version))
    return out


class DeterminismTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_root(self.tmp.name, skills="real")

    def test_generators_are_deterministic(self):
        self.assertEqual(generated(self.root), generated(self.root))

    def test_no_skills_dir_emits_nothing(self):
        root = make_root(tempfile.mkdtemp(), skills=None)
        self.addCleanup(shutil.rmtree, root)
        for mod in GENERATORS:
            with self.subTest(mod=mod.__name__):
                self.assertEqual(mod.gen(root, VERSION), {})

    def test_generated_paths_are_safe(self):
        for rel in generated(self.root):
            with self.subTest(rel=rel):
                path = PurePosixPath(rel)
                self.assertFalse(path.is_absolute())
                self.assertNotIn("..", path.parts)
                self.assertNotEqual(path.parts[0], ".git")

    def test_generated_markdown_follows_prose_rules(self):
        for rel, content in generated(self.root).items():
            if not rel.endswith(".md"):
                continue
            with self.subTest(rel=rel):
                self.assertNotIn(EM_DASH, content)
                self.assertIsNone(BANNED_WORDS.search(content))

    def test_all_generated_json_parses(self):
        for rel, content in generated(self.root).items():
            if rel.endswith(".json"):
                with self.subTest(rel=rel):
                    json.loads(content)


class AgentPluginsShapeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_root(self.tmp.name, skills="real")
        self.files = gen_agent_plugins.gen(self.root, VERSION)

    def test_root_plugin_json_shape(self):
        data = json.loads(self.files["plugin.json"])
        self.assertEqual(data["$schema"], AGENT_PLUGINS_SCHEMA)
        self.assertLessEqual(set(data), AGENT_PLUGINS_FIELDS)
        self.assertEqual(data["name"], "betterterms")
        self.assertTrue(AGENT_PLUGINS_NAME.fullmatch(data["name"]))
        self.assertNotIn("--", data["name"])
        self.assertNotIn("..", data["name"])
        self.assertEqual(data["version"], VERSION)
        self.assertEqual(data["description"], KIT["description"])
        self.assertLessEqual(
            set(data["author"]), {"name", "email", "url"}
        )
        self.assertEqual(data["license"], KIT["license"])

    def test_skills_key_names_the_tree(self):
        data = json.loads(self.files["plugin.json"])
        self.assertEqual(data["skills"], "./skills/")

    def test_no_inline_component_fields(self):
        # Component discovery is fixed-location only: no hooks,
        # mcpServers or commands keys may appear in the manifest.
        data = json.loads(self.files["plugin.json"])
        for key in ("hooks", "mcpServers", "commands"):
            self.assertNotIn(key, data)


class VersionSyncTest(unittest.TestCase):
    """Every generated manifest's version field tracks VERSION."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_root(self.tmp.name, skills="real")
        shutil.copytree(
            REPO / "scripts", self.root / "scripts",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    def test_every_manifest_version_matches_version_file(self):
        for rel, content in generated(self.root).items():
            if not rel.endswith(".json"):
                continue
            data = json.loads(content)
            if "version" in data:
                with self.subTest(rel=rel):
                    self.assertEqual(data["version"], VERSION)

    def test_bump_check_passes_after_build(self):
        for name, argv in (
            ("build", []),
            ("bump-version", ["--check"]),
        ):
            proc = subprocess.run(
                [sys.executable, str(self.root / "scripts" / name), *argv],
                cwd=self.root, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(
                proc.returncode, 0, name + ": " + proc.stdout + proc.stderr
            )
        manifests = [
            p for p in self.root.rglob("*.json")
            if "__pycache__" not in p.parts
        ]
        for path in manifests:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "version" in data:
                with self.subTest(rel=path.relative_to(self.root)):
                    self.assertEqual(data["version"], VERSION)


if __name__ == "__main__":
    unittest.main()
