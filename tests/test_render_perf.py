"""Render performance: ``{option:L}`` and ``{fact:id}`` resolve through
index dicts built once per render, so a large plan and a 64 KB
template render in well under a second."""

import time
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
from btlib import render


class RenderPerfTest(BtTestCase):
    def make_case(self, direction="pay", floor=1200):
        case_id, case_dir = new_case(self.home, direction=direction)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, direction=direction),
            plan=plan_for(direction, floor),
            floor=floor,
        )
        return case_id

    def gate(self, case_id, draft):
        path = write_draft(self.tmp, draft)
        return run_bt_json(self.home, "gate", case_id, "--draft",
                           str(path))

    def test_placeholder_lookups_do_not_scan_the_plan(self):
        # {option} and {fact} resolve through index dicts built once
        # per render, so lookup cost does not scale with plan size.
        # A counting dict proves no per-placeholder scan remains.
        class Counting(dict):
            calls = 0

            def get(self, *a, **kw):
                Counting.calls += 1
                return super().get(*a, **kw)

        Counting.calls = 0
        plan = {
            "target": 5,
            "options": [
                Counting(label="o%d" % i, value=5, terms="x")
                for i in range(2600)
            ],
            "ladder": [],
            "facts": [
                Counting(id="f%d" % i, text="x", source="s")
                for i in range(2600)
            ],
        }
        template = " ".join(
            "{option:o%d} {fact:f%d}" % (i % 2600, i % 2600)
            for i in range(400)
        )
        render.render(template, None, "once", plan, "once", [])
        # Index build is one pass per list plus a few reads per
        # placeholder; a scan per placeholder would be ~1M gets.
        self.assertLess(Counting.calls, 50000)

    def test_large_plan_and_template_render_fast(self):
        # 2,600 facts, 2,600 options, and a 64 KB template render in
        # under a second.
        plan = {
            "target": 5,
            "options": [
                {"label": "o%d" % i, "value": 5, "terms": "x"}
                for i in range(2600)
            ],
            "ladder": [],
            "facts": [
                {"id": "f%d" % i, "text": "x", "source": "s"}
                for i in range(2600)
            ],
        }
        parts, size, i = [], 0, 0
        while size < 64 * 1024:
            piece = "{option:o%d} {fact:f%d} " % (i % 2600, i % 2600)
            parts.append(piece)
            size += len(piece)
            i += 1
        start = time.monotonic()
        find = render.render(
            "".join(parts), None, "once", plan, "once", []
        )
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertFalse(find.errors)

    def test_64kb_template_gate_run_under_one_second(self):
        case_id = self.make_case()
        template = "word " * 13000  # 65000 bytes, under the 64 KB cap
        start = time.monotonic()
        proc, out = self.gate(case_id, send_draft(template=template))
        elapsed = time.monotonic() - start
        self.assertEqual(proc.returncode, 0, out)
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
