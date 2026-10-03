"""Source records: ``bt.py source add`` validates a record piped on
stdin and writes ``sources/<n>.yaml``; ``source list`` reads them back
and ``source stale`` flags records too old to rely on."""

import unittest
from datetime import date, timedelta
from pathlib import Path

from bt_helpers import BtTestCase, new_case, run_bt_json
from btlib import yaml


def record(**kw):
    rec = {
        "url": "https://provider.example/cancel",
        "read_at": "2026-10-01",
        "quote": "You may cancel online at any time.",
        "trust": "official",
        "used_for": "cancellation policy",
    }
    rec.update(kw)
    return rec


class SourceAddTest(BtTestCase):
    def add(self, case_id, text=""):
        return run_bt_json(self.home, "source", "add", case_id, stdin=text)

    def test_add_writes_numbered_record(self):
        case_id, case_dir = new_case(self.home)
        proc, out = self.add(case_id, yaml.dump(record()))
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["id"], "1")
        path = Path(out["path"])
        self.assertEqual(path, case_dir / "sources" / "1.yaml")
        stored = yaml.load(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["url"], "https://provider.example/cancel")
        self.assertEqual(stored["quote"], "You may cancel online at any time.")
        self.assertEqual(stored["trust"], "official")
        self.assertEqual(stored["used_for"], "cancellation policy")
        self.assertEqual(str(stored["read_at"]), "2026-10-01")

    def test_add_increments_id(self):
        case_id, case_dir = new_case(self.home)
        _, first = self.add(case_id, yaml.dump(record()))
        _, second = self.add(
            case_id, yaml.dump(record(url="https://news.example/x", trust="press"))
        )
        self.assertEqual(first["id"], "1")
        self.assertEqual(second["id"], "2")
        self.assertTrue((case_dir / "sources" / "2.yaml").is_file())

    def test_add_requires_all_fields(self):
        case_id, case_dir = new_case(self.home)
        for field in ("url", "read_at", "quote", "trust", "used_for"):
            rec = record()
            del rec[field]
            with self.subTest(missing=field):
                proc, out = self.add(case_id, yaml.dump(rec))
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)
        self.assertEqual(list((case_dir / "sources").iterdir()), [])

    def test_add_rejects_empty_strings(self):
        case_id, _ = new_case(self.home)
        for field in ("url", "quote", "used_for"):
            with self.subTest(field=field):
                proc, out = self.add(case_id, yaml.dump(record(**{field: "  "})))
                self.assertEqual(proc.returncode, 2, out)

    def test_add_rejects_bad_trust(self):
        case_id, _ = new_case(self.home)
        for trust in ("blog", "", "verified", None):
            with self.subTest(trust=trust):
                proc, out = self.add(case_id, yaml.dump(record(trust=trust)))
                self.assertEqual(proc.returncode, 2, out)

    def test_add_rejects_bad_read_at(self):
        case_id, _ = new_case(self.home)
        for read_at in ("yesterday", "10/01/2026", "2026-13-40", 42):
            with self.subTest(read_at=read_at):
                proc, out = self.add(case_id, yaml.dump(record(read_at=read_at)))
                self.assertEqual(proc.returncode, 2, out)

    def test_add_normalizes_datetime_read_at(self):
        case_id, case_dir = new_case(self.home)
        proc, out = self.add(case_id, yaml.dump(record(read_at="2026-10-01T14:30:00")))
        self.assertEqual(proc.returncode, 0, out)
        stored = yaml.load((case_dir / "sources" / "1.yaml").read_text())
        self.assertEqual(str(stored["read_at"]), "2026-10-01")

    def test_add_rejects_unknown_fields(self):
        case_id, _ = new_case(self.home)
        proc, out = self.add(case_id, yaml.dump(record(notes="extra")))
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)

    def test_add_rejects_non_mapping_stdin(self):
        case_id, _ = new_case(self.home)
        for text in ("", "just a string\n", "- a\n- b\n"):
            with self.subTest(text=text):
                proc, out = self.add(case_id, text)
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)

    def test_add_bad_yaml_errors(self):
        case_id, _ = new_case(self.home)
        proc, out = self.add(case_id, "url: [unclosed\n")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_add_unknown_case_errors(self):
        proc, out = run_bt_json(
            self.home, "source", "add", "nope-20000101-0000",
            stdin=yaml.dump(record()),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)


class SourceListTest(BtTestCase):
    def test_list_returns_records_in_order(self):
        case_id, _ = new_case(self.home)
        run_bt_json(self.home, "source", "add", case_id,
                    stdin=yaml.dump(record(quote="first")))
        run_bt_json(self.home, "source", "add", case_id,
                    stdin=yaml.dump(record(quote="second", trust="forum")))
        proc, out = run_bt_json(self.home, "source", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual([s["id"] for s in out["sources"]], ["1", "2"])
        self.assertEqual(out["sources"][0]["quote"], "first")
        self.assertEqual(out["sources"][1]["trust"], "forum")
        self.assertEqual(out["sources"][0]["read_at"], "2026-10-01")

    def test_list_empty(self):
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(self.home, "source", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["sources"], [])

    def test_list_ignores_non_record_files(self):
        case_id, case_dir = new_case(self.home)
        run_bt_json(self.home, "source", "add", case_id, stdin=yaml.dump(record()))
        (case_dir / "sources" / "notes.md").write_text("scratch")
        (case_dir / "sources" / "abc.yaml").write_text("url: x\n")
        proc, out = run_bt_json(self.home, "source", "list", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(len(out["sources"]), 1)

    def test_list_malformed_record_errors(self):
        case_id, case_dir = new_case(self.home)
        (case_dir / "sources" / "3.yaml").write_text("url: [unclosed\n")
        proc, out = run_bt_json(self.home, "source", "list", case_id)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)


class SourceStaleTest(BtTestCase):
    def add_dated(self, case_id, days_ago):
        read_at = (date.today() - timedelta(days=days_ago)).isoformat()
        proc, out = run_bt_json(
            self.home, "source", "add", case_id,
            stdin=yaml.dump(record(read_at=read_at)),
        )
        assert proc.returncode == 0, out
        return out["id"]

    def test_stale_flags_old_records(self):
        case_id, _ = new_case(self.home)
        old = self.add_dated(case_id, 120)
        self.add_dated(case_id, 10)
        proc, out = run_bt_json(self.home, "source", "stale", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["days"], 90)
        self.assertEqual([s["id"] for s in out["stale"]], [old])
        self.assertEqual(out["stale"][0]["age_days"], 120)

    def test_stale_boundary_is_strictly_older(self):
        case_id, _ = new_case(self.home)
        edge = self.add_dated(case_id, 90)
        over = self.add_dated(case_id, 91)
        proc, out = run_bt_json(
            self.home, "source", "stale", case_id, "--days", "90"
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual([s["id"] for s in out["stale"]], [over])

    def test_stale_days_option(self):
        case_id, _ = new_case(self.home)
        seen = self.add_dated(case_id, 45)
        proc, out = run_bt_json(
            self.home, "source", "stale", case_id, "--days", "30"
        )
        self.assertEqual([s["id"] for s in out["stale"]], [seen])
        proc, out = run_bt_json(
            self.home, "source", "stale", case_id, "--days", "60"
        )
        self.assertEqual(out["stale"], [])

    def test_stale_flags_unreadable_date(self):
        # A record whose date cannot be read cannot be shown fresh, so
        # it is flagged for re-check rather than silently trusted.
        case_id, case_dir = new_case(self.home)
        self.add_dated(case_id, 5)
        (case_dir / "sources" / "7.yaml").write_text(
            yaml.dump({"url": "https://x.example", "read_at": "someday",
                       "quote": "q", "trust": "press", "used_for": "u"})
        )
        proc, out = run_bt_json(self.home, "source", "stale", case_id)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual([s["id"] for s in out["stale"]], ["7"])
        self.assertIsNone(out["stale"][0]["age_days"])

    def test_stale_negative_days_errors(self):
        case_id, _ = new_case(self.home)
        proc, out = run_bt_json(
            self.home, "source", "stale", case_id, "--days", "-5"
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_stale_unknown_case_errors(self):
        proc, out = run_bt_json(
            self.home, "source", "stale", "nope-20000101-0000"
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
