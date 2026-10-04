"""vendor-into-repo merges the plugin keys into .claude/settings.json."""

import json
import tempfile
import unittest
from pathlib import Path

from test_install import make_repo, run

MARKETPLACE = {
    "source": {"source": "github", "repo": "hanselhansel/betterterms"}
}


class VendorSettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = make_repo(self.tmp)
        self.target = self.tmp / "consumer"
        self.target.mkdir()
        self.settings = self.target / ".claude" / "settings.json"

    def vendor(self, *args):
        return run(self.repo, "vendor-into-repo", str(self.target), *args)

    def read(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def test_creates_settings_when_absent(self):
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        settings = self.read()
        self.assertEqual(
            settings["extraKnownMarketplaces"],
            {"betterterms": MARKETPLACE},
        )
        self.assertEqual(
            settings["enabledPlugins"], {"betterterms@betterterms": True}
        )
        self.assertIn(".claude/settings.json", proc.stdout)

    def test_merges_into_existing_settings_keeping_other_keys(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["Bash(python3:*)"]},
                    "extraKnownMarketplaces": {
                        "acme": {
                            "source": {"source": "github", "repo": "acme/kit"}
                        }
                    },
                    "enabledPlugins": {"acme@acme": False},
                    "model": "sonnet",
                }
            ),
            encoding="utf-8",
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        settings = self.read()
        self.assertEqual(
            settings["permissions"], {"allow": ["Bash(python3:*)"]}
        )
        self.assertEqual(settings["model"], "sonnet")
        self.assertEqual(
            settings["extraKnownMarketplaces"]["acme"],
            {"source": {"source": "github", "repo": "acme/kit"}},
        )
        self.assertEqual(
            settings["extraKnownMarketplaces"]["betterterms"], MARKETPLACE
        )
        self.assertIs(settings["enabledPlugins"]["acme@acme"], False)
        self.assertIs(
            settings["enabledPlugins"]["betterterms@betterterms"], True
        )

    def test_settings_merge_is_idempotent(self):
        for _ in range(2):
            proc = self.vendor()
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        settings = self.read()
        self.assertEqual(
            list(settings["extraKnownMarketplaces"]), ["betterterms"]
        )
        self.assertEqual(
            settings["enabledPlugins"], {"betterterms@betterterms": True}
        )

    def test_no_plugin_flag_skips_settings(self):
        proc = self.vendor("--no-plugin")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.settings.exists())
        self.assertTrue(
            (
                self.target / ".claude/skills/betterterms-start/SKILL.md"
            ).is_file()
        )

    def test_no_plugin_ignores_invalid_settings(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        proc = self.vendor("--no-plugin")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.settings.read_text(), "{ not json")

    def test_invalid_settings_json_exits_2_without_writing(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        proc = self.vendor()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(self.settings.read_text(), "{ not json")
        self.assertFalse((self.target / ".claude" / "skills").exists())


if __name__ == "__main__":
    unittest.main()
