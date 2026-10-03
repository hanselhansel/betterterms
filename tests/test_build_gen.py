import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from _lib import gen_claude, gen_codex  # noqa: E402
from _lib.checks_prose import BANNED_WORDS, EM_DASH  # noqa: E402
from test_scripts import load_script  # noqa: E402

VERSION = (REPO / "VERSION").read_text(encoding="utf-8").strip()
KIT = json.loads((REPO / "kit.config.json").read_text(encoding="utf-8"))

PLUGIN_JSON_KEYS = {"name", "version", "description", "author",
                    "repository", "license", "keywords"}


def make_root(tmp, skills=None):
    """A throwaway repo root for generator calls: VERSION and
    kit.config.json copied. skills='real' copies the tree, 'fake'
    writes two toy packs, None leaves skills/ absent."""
    root = Path(tmp)
    for name in ("VERSION", "kit.config.json"):
        shutil.copy2(REPO / name, root / name)
    if skills == "real":
        shutil.copytree(
            REPO / "skills", root / "skills",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    elif skills == "fake":
        pack = root / "skills" / "betterterms-foo"
        pack.mkdir(parents=True)
        (pack / "SKILL.md").write_text(
            "---\nname: betterterms-foo\ndescription: Foo pack.\n---\n\nBody.\n"
        )
        (pack / "pack.yaml").write_text(
            "name: betterterms-foo\ncommand: foo-cmd\nmode: act\n"
            "direction: pay\ntriggers: []\n"
        )
        other = root / "skills" / "betterterms-nocmd"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text(
            "---\nname: betterterms-nocmd\ndescription: No command.\n---\n\nBody.\n"
        )
        (other / "pack.yaml").write_text("name: betterterms-nocmd\nmode: act\n")
    return root


def generated(root, version=VERSION):
    out = {}
    for mod in (gen_claude, gen_codex):
        out.update(mod.gen(root, version))
    return out


def _has_key(value, key):
    if isinstance(value, dict):
        return key in value or any(_has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_has_key(v, key) for v in value)
    return False


class DeterminismTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_root(self.tmp.name, skills="real")

    def test_generators_are_deterministic(self):
        self.assertEqual(generated(self.root), generated(self.root))

    def test_build_twice_writes_identical_files(self):
        shutil.copytree(
            REPO / "scripts", self.root / "scripts",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        snapshots = []
        for _ in range(2):
            proc = subprocess.run(
                [sys.executable, str(self.root / "scripts" / "build")],
                cwd=self.root, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            snaps = {
                str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*"))
                if p.is_file()
            }
            snapshots.append(snaps)
        self.assertEqual(snapshots[0], snapshots[1])

    def test_build_check_passes_after_build(self):
        shutil.copytree(
            REPO / "scripts", self.root / "scripts",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        build = load_script(self.root, "build", "bt_build_gen_test")
        self.assertEqual(build.main([]), 0)
        self.assertEqual(build.main(["--check"]), 0)
        for rel, content in build.expected(self.root).items():
            self.assertEqual(
                (self.root / rel).read_text(encoding="utf-8"), content
            )


class ShapeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_root(self.tmp.name, skills="real")
        self.files = generated(self.root)

    def test_claude_plugin_json_shape(self):
        data = json.loads(self.files[".claude-plugin/plugin.json"])
        self.assertEqual(set(data), PLUGIN_JSON_KEYS)
        self.assertEqual(data["name"], "betterterms")
        self.assertEqual(data["version"], VERSION)
        self.assertEqual(data["description"], KIT["description"])
        self.assertEqual(data["author"]["name"], KIT["author"]["name"])
        self.assertEqual(data["repository"], KIT["repository"])
        self.assertEqual(data["license"], KIT["license"])
        self.assertEqual(data["keywords"], KIT["keywords"])

    def test_claude_marketplace_json_shape(self):
        data = json.loads(self.files[".claude-plugin/marketplace.json"])
        self.assertEqual(data["name"], "betterterms")
        self.assertEqual(data["description"], KIT["description"])
        self.assertEqual(data["owner"]["name"], KIT["author"]["name"])
        self.assertEqual(len(data["plugins"]), 1)
        plugin = data["plugins"][0]
        self.assertEqual(plugin["name"], "betterterms")
        self.assertEqual(plugin["source"], "./")
        self.assertIn("description", plugin)

    def test_claude_marketplace_lists_mod_when_present(self):
        mod = self.root / "mod" / ".claude-plugin"
        mod.mkdir(parents=True)
        (mod / "plugin.json").write_text(json.dumps({
            "name": "betterterms-mod",
            "description": "Test mod.",
            "version": "0.0.0",
            "author": {"name": "x"},
        }))
        data = json.loads(gen_claude.gen(self.root, VERSION)
                          [".claude-plugin/marketplace.json"])
        self.assertEqual(len(data["plugins"]), 2)
        entry = data["plugins"][1]
        self.assertEqual(entry["name"], "betterterms-mod")
        self.assertEqual(entry["source"], "./mod")
        self.assertEqual(entry["description"], "Test mod.")

    def test_claude_marketplace_mod_entry_without_manifest(self):
        (self.root / "mod").mkdir()
        data = json.loads(gen_claude.gen(self.root, VERSION)
                          [".claude-plugin/marketplace.json"])
        entry = data["plugins"][1]
        self.assertEqual(entry["name"], "betterterms-mod")
        self.assertEqual(entry["source"], "./mod")
        self.assertIn("description", entry)

    def test_codex_plugin_json_shape(self):
        data = json.loads(self.files[".codex-plugin/plugin.json"])
        self.assertEqual(data["name"], "betterterms")
        self.assertEqual(data["version"], VERSION)
        self.assertEqual(data["skills"], "./skills/")
        self.assertEqual(data["license"], KIT["license"])

    def test_codex_marketplace_json_shape(self):
        data = json.loads(self.files[".agents/plugins/marketplace.json"])
        self.assertEqual(data["name"], "betterterms")
        self.assertEqual(len(data["plugins"]), 1)
        plugin = data["plugins"][0]
        self.assertEqual(plugin["name"], "betterterms")
        self.assertEqual(plugin["source"], {"source": "url", "url": "./"})

    def test_version_only_in_plugin_json(self):
        for rel, content in self.files.items():
            path = PurePosixPath(rel)
            if "marketplace" in path.name:
                with self.subTest(rel=rel):
                    data = json.loads(content)
                    self.assertFalse(_has_key(data, "version"))
            if path.name == "plugin.json":
                with self.subTest(rel=rel):
                    data = json.loads(content)
                    self.assertEqual(data["version"], VERSION)

    def test_entry_command_invokes_start_skill(self):
        content = self.files["commands/betterterms.md"]
        self.assertIn("betterterms-start", content)

    def test_generated_paths_are_safe(self):
        for rel in self.files:
            with self.subTest(rel=rel):
                path = PurePosixPath(rel)
                self.assertFalse(path.is_absolute())
                self.assertNotIn("..", path.parts)
                self.assertNotEqual(path.parts[0], ".git")

    def test_generated_markdown_follows_prose_rules(self):
        for rel, content in self.files.items():
            if not rel.endswith(".md"):
                continue
            with self.subTest(rel=rel):
                self.assertNotIn(EM_DASH, content)
                self.assertIsNone(BANNED_WORDS.search(content))


class PackCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_root(self.tmp.name, skills="fake")

    def test_pack_command_generates_command_file(self):
        files = gen_claude.gen(self.root, VERSION)
        self.assertIn("commands/foo-cmd.md", files)
        self.assertIn("betterterms-foo", files["commands/foo-cmd.md"])

    def test_pack_without_command_generates_nothing(self):
        files = gen_claude.gen(self.root, VERSION)
        self.assertNotIn("commands/nocmd.md", files)
        self.assertNotIn("commands/betterterms-nocmd.md", files)

    def test_unsafe_command_name_raises(self):
        pack = self.root / "skills" / "betterterms-foo" / "pack.yaml"
        pack.write_text("command: ../evil\n")
        with self.assertRaises(ValueError):
            gen_claude.gen(self.root, VERSION)

    def test_empty_skills_dir_still_emits_entry_command(self):
        root = make_root(tempfile.mkdtemp(), skills=None)
        self.addCleanup(shutil.rmtree, root)
        (root / "skills").mkdir()
        files = gen_claude.gen(root, VERSION)
        self.assertIn("commands/betterterms.md", files)
        commands = [r for r in files if r.startswith("commands/")]
        self.assertEqual(commands, ["commands/betterterms.md"])

    def test_no_skills_dir_emits_nothing(self):
        root = make_root(tempfile.mkdtemp(), skills=None)
        self.addCleanup(shutil.rmtree, root)
        self.assertEqual(gen_claude.gen(root, VERSION), {})
        self.assertEqual(gen_codex.gen(root, VERSION), {})


if __name__ == "__main__":
    unittest.main()
