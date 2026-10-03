import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERIFY = REPO / "scripts" / "verify"

sys.path.insert(0, str(REPO / "scripts"))

from _lib import checks_scan  # noqa: E402


def load_verify():
    loader = importlib.machinery.SourceFileLoader(
        "bt_verify_under_test", str(VERIFY)
    )
    spec = importlib.util.spec_from_loader("bt_verify_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


VERIFY_MOD = load_verify()

from _lib import checks_packs  # noqa: E402

VALID_PACK = """\
name: x
command: x
mode: act
direction: pay
triggers:
  - lower my bill
  - too expensive
intake:
  - "How much did you use it in the last 90 days?"
discovery:
  - source: email
    find: "receipts and renewal notices"
    window_days: 400
research:
  - kind: policy
  - kind: pricing
savings:
  formula: "(before - after) * periods_per_year"
"""


def make_repo_root(path):
    (path / "VERSION").write_text("0.1.0\n")
    (path / "kit.config.json").write_text('{"name": "x"}\n')


def run_check(root):
    checks_scan.file_list.cache_clear()
    return checks_packs.check_pack_schema(root)


class PackSchemaTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        make_repo_root(self.root)

    def add_pack(self, text=VALID_PACK, folder="betterterms-x"):
        d = self.root / "skills" / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / "pack.yaml").write_text(text)
        return d / "pack.yaml"

    def test_skip_when_no_packs(self):
        status, detail = run_check(self.root)
        self.assertEqual(status, "SKIP")
        self.assertIn("pack.yaml", detail)

    def test_non_betterterms_pack_yaml_ignored(self):
        self.add_pack(folder="other-thing")
        status, _ = run_check(self.root)
        self.assertEqual(status, "SKIP")

    def test_valid_pack_passes(self):
        self.add_pack()
        status, detail = run_check(self.root)
        self.assertEqual((status, detail), ("PASS", ""))

    def test_missing_key_fails(self):
        self.add_pack(VALID_PACK.replace("savings:\n  formula: \"(before - after) * periods_per_year\"\n", ""))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("savings", detail)

    def test_extra_key_fails(self):
        self.add_pack(VALID_PACK + "bonus: 1\n")
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("bonus", detail)

    def test_bad_mode_fails(self):
        self.add_pack(VALID_PACK.replace("mode: act", "mode: freestyle"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("mode", detail)

    def test_bad_direction_fails(self):
        self.add_pack(VALID_PACK.replace("direction: pay", "direction: sideways"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("direction", detail)

    def test_name_must_match_folder(self):
        self.add_pack(VALID_PACK.replace("name: x", "name: y"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("name", detail)

    def test_triggers_must_be_nonempty_list(self):
        self.add_pack(VALID_PACK.replace(
            "triggers:\n  - lower my bill\n  - too expensive\n", "triggers: []\n"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("triggers", detail)

    def test_intake_entries_must_be_strings(self):
        self.add_pack(VALID_PACK.replace(
            '  - "How much did you use it in the last 90 days?"\n',
            "  - {q: 3}\n"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("intake", detail)

    def test_discovery_entry_shape_fails(self):
        self.add_pack(VALID_PACK.replace(
            "    window_days: 400\n", "    window_days: soon\n"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("window_days", detail)
        self.add_pack(VALID_PACK.replace(
            "    window_days: 400\n", "    window_days: 400\n    extra: x\n"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")

    def test_research_kind_enum_fails(self):
        self.add_pack(VALID_PACK.replace(
            "  - kind: pricing\n", "  - kind: vibes\n"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("kind", detail)

    def test_savings_must_have_formula(self):
        self.add_pack(VALID_PACK.replace(
            '  formula: "(before - after) * periods_per_year"\n',
            "  math: \"x\"\n"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("savings", detail)

    def test_unparseable_yaml_fails(self):
        self.add_pack("name: [unclosed\n")
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("pack.yaml", detail)

    def test_non_mapping_yaml_fails(self):
        self.add_pack("- just\n- a\n- list\n")
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")

    def test_duplicate_command_fails(self):
        self.add_pack(folder="betterterms-a",
                      text=VALID_PACK.replace("name: x", "name: a"))
        self.add_pack(folder="betterterms-b",
                      text=VALID_PACK.replace("name: x", "name: b"))
        status, detail = run_check(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("command", detail)

    def test_check_is_registered(self):
        names = [name for name, _fn in VERIFY_MOD.CHECKS]
        self.assertIn("pack-schema", names)

    def test_real_repo_packs_validate(self):
        checks_scan.file_list.cache_clear()
        status, detail = checks_packs.check_pack_schema(REPO)
        self.assertEqual(status, "PASS", detail)


if __name__ == "__main__":
    unittest.main()
