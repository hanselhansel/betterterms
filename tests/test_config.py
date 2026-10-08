"""config.yaml (spec 5): defaults when missing, plain errors naming
the key on bad values, unknown keys warned to stderr, 0600 file mode,
prefill into new cases, and the gate never reading it."""

import os
import stat
import unittest

from bt_helpers import (
    BRIEF_PAY,
    BtTestCase,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import yaml

DEFAULTS = {
    "autonomy": 2,
    "currency": "USD",
    "sign_off": "",
    "voice_notes": "",
}


class ConfigTest(BtTestCase):
    def write_config(self, data):
        self.home.mkdir(parents=True, exist_ok=True)
        text = yaml.dump(data) if isinstance(data, dict) else data
        (self.home / "config.yaml").write_text(text)

    def test_config_defaults_when_missing(self):
        proc, out = run_bt_json(self.home, "config", "show")
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["config"], DEFAULTS)
        self.assertFalse((self.home / "config.yaml").exists())

    def test_config_bad_autonomy_names_key(self):
        self.write_config({"autonomy": 7})
        proc, out = run_bt_json(self.home, "config", "show")
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("autonomy", out["error"])
        proc, out = run_bt_json(
            self.home, "config", "set", "autonomy", "7"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("autonomy", out["error"])

    def test_config_bad_currency_names_key(self):
        self.write_config({"currency": "dollars"})
        proc, out = run_bt_json(self.home, "config", "show")
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("currency", out["error"])

    def test_config_unknown_key_warns_not_errors(self):
        self.write_config({"autonomy": 3, "mystery": 1})
        proc, out = run_bt_json(self.home, "config", "show")
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("mystery", proc.stderr)
        self.assertNotIn("mystery", out["config"])

    def test_config_set_unknown_key_errors(self):
        proc, out = run_bt_json(
            self.home, "config", "set", "mystery", "1"
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("mystery", out["error"])

    def test_config_file_mode_0600(self):
        proc, out = run_bt_json(
            self.home, "config", "set", "sign_off", "A User"
        )
        self.assertEqual(proc.returncode, 0, out)
        path = self.home / "config.yaml"
        self.assertTrue(path.is_file())
        mode = stat.S_IMODE(os.stat(path).st_mode)
        self.assertEqual(mode, 0o600, oct(mode))
        self.assertEqual(
            yaml.load(path.read_text())["sign_off"], "A User"
        )

    def test_new_case_prefills_from_config(self):
        self.write_config(
            {"autonomy": 3, "currency": "EUR", "sign_off": "A User"}
        )
        case_id, case_dir = new_case(self.home)
        brief = yaml.load((case_dir / "brief.yaml").read_text())
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(brief["autonomy"], 3)
        self.assertEqual(plan["currency"], "EUR")

    def test_new_case_without_config_keeps_mode_defaults(self):
        case_id, case_dir = new_case(self.home, mode="coach")
        brief = yaml.load((case_dir / "brief.yaml").read_text())
        plan = yaml.load((case_dir / "plan.yaml").read_text())
        self.assertEqual(brief["autonomy"], 1)
        self.assertEqual(plan["currency"], "USD")

    def test_gate_ignores_config(self):
        case_id, case_dir = new_case(self.home)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY),
            plan=plan_for("pay", 1200),
            floor=1200,
        )
        draft = write_draft(
            self.tmp, send_draft(template="asking for a better rate")
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(draft)
        )
        self.assertEqual(proc.returncode, 0, out)
        self.write_config(
            {
                "autonomy": 1,
                "currency": "EUR",
                "sign_off": "x",
                "voice_notes": "y",
            }
        )
        proc, out2 = run_bt_json(
            self.home, "gate", case_id, "--draft", str(draft)
        )
        self.assertEqual(proc.returncode, 0, out2)
        self.assertEqual(out2["result"], "pass")
        self.assertEqual(out, out2)


if __name__ == "__main__":
    unittest.main()
