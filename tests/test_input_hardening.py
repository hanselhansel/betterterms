"""Step-2 review fixes, second round: every YAML file bt.py reads goes
through one helper that refuses files over 64 KB and documents nested
deeper than 32 levels before or during parsing (a block for draft and
inbound, an error for brief and plan); ``case show`` serializes date
mapping keys instead of tracebacking; draft values that are not short
strings (a 4300+ digit integer breaks repr/str outright) block with
exit 1 instead of crashing out as exit 2; and a block drops the
converted-limit and same-digits reasons that would each leak one bit
about the floor (0007).
"""

import json
import time
import unittest

from bt_helpers import (
    BRIEF_PAY,
    PLAN_BILLS,
    BtTestCase,
    new_case,
    plan_for,
    run_bt,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import BtError, gate, inputs, yaml

LIMITS = "outside your limits; escalate to the user"


class HardenedCase(BtTestCase):
    def make_case(self, direction="pay", floor=1200, plan=None, brief=None):
        case_id, case_dir = new_case(self.home, direction=direction)
        b = dict(BRIEF_PAY, direction=direction)
        if brief:
            b.update(brief)
        write_case_files(
            case_dir,
            brief=b,
            plan=plan_for(direction, floor) if plan is None else plan,
            floor=floor,
        )
        return case_id, case_dir

    def gate(self, case_id, draft, inbound=None):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        return run_bt_json(self.home, *args)


class InputBoundsTest(HardenedCase):
    def test_draft_over_64kb_blocks_not_errors(self):
        # A draft file over 64 KB is refused before parsing: a block
        # (exit 1), never a parse or usage error (exit 2).
        case_id, _ = self.make_case()
        path = self.tmp / "draft.yaml"
        path.write_text(
            "action: send\noffer: 1100\ntemplate: hi\npad: "
            + "x" * 70000 + "\n"
        )
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("64 KB", " ".join(out["reasons"]))
        self.assertIsNone(out["rendered"])

    def test_inbound_over_64kb_blocks_gate_and_score(self):
        case_id, _ = self.make_case()
        ipath = self.tmp / "inbound.yaml"
        ipath.write_text("offer: 1100\ntext: " + "x" * 70000 + "\n")
        draft = write_draft(self.tmp, send_draft())
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(draft),
            "--inbound", str(ipath),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        proc, out = run_bt_json(
            self.home, "score", case_id, "--inbound", str(ipath)
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")

    def test_oversized_brief_errors(self):
        # Case files fail as errors (exit 2): a refused brief or plan
        # is a broken case, not a hostile draft.
        case_id, case_dir = self.make_case()
        (case_dir / "brief.yaml").write_text(
            "pack: bills\nmode: act\ndirection: pay\nautonomy: 2\n"
            "pad: " + "x" * 70000 + "\n"
        )
        draft = write_draft(self.tmp, send_draft())
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(draft)
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)
        proc, out = run_bt_json(self.home, "case", "show", case_id)
        self.assertEqual(proc.returncode, 2, out)

    def test_oversized_plan_errors(self):
        case_id, case_dir = self.make_case()
        (case_dir / "plan.yaml").write_text(
            "target: 1000\ncurrency: USD\npad: " + "x" * 70000 + "\n"
        )
        draft = write_draft(self.tmp, send_draft())
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(draft)
        )
        self.assertEqual(proc.returncode, 2, out)
        self.assertIn("error", out)
        proc, out = run_bt_json(self.home, "case", "show", case_id)
        self.assertEqual(proc.returncode, 2, out)

    def test_deep_flow_draft_blocks_under_one_second(self):
        # A 64 KB draft with flow lists nested 250 deep is refused
        # during parsing: a fast block, never a recursion-limit error.
        case_id, _ = self.make_case()
        deep = "[" * 250 + "]" * 250
        text = (
            "action: send\noffer: 1100\ntemplate: hi\nclaims: []\n"
            f"deep: {deep}\npad: {'y' * 63000}\n"
        )
        path = self.tmp / "draft.yaml"
        path.write_text(text)
        self.assertLess(path.stat().st_size, 64 * 1024)
        start = time.monotonic()
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        elapsed = time.monotonic() - start
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("nesting", " ".join(out["reasons"]))
        self.assertLess(elapsed, 1.0)

    def test_deep_block_nesting_draft_blocks(self):
        case_id, _ = self.make_case()
        text = "action: send\noffer: 1100\ntemplate: hi\nk:\n"
        text += "".join("  " * i + f"k{i}:\n" for i in range(1, 40))
        path = self.tmp / "draft.yaml"
        path.write_text(text)
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("nesting", " ".join(out["reasons"]))

    def test_nesting_depth_boundary(self):
        # The bound is "deeper than 32": a value nested exactly 32
        # levels parses and reports as an unknown key; 33 refuses.
        case_id, _ = self.make_case()
        for n, reason in ((31, "unknown draft keys"), (32, "nesting")):
            with self.subTest(depth=n):
                deep = "[" * n + "1" + "]" * n
                path = self.tmp / "draft.yaml"
                path.write_text(
                    "action: send\noffer: 1100\ntemplate: hi\n"
                    f"deep: {deep}\n"
                )
                proc, out = run_bt_json(
                    self.home, "gate", case_id, "--draft", str(path)
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(reason, " ".join(out["reasons"]), out)

    def test_helper_failure_classes(self):
        # Missing file, bad YAML and non-mapping stay BtError (exit 2
        # semantics); the size and depth refusals are UnsafeInput.
        with self.assertRaises(BtError) as cm:
            inputs.load_yaml_file(self.tmp / "none.yaml", "x")
        self.assertNotIsInstance(cm.exception, inputs.UnsafeInput)
        bad = self.tmp / "bad.yaml"
        bad.write_text("{unclosed: [")
        with self.assertRaises(BtError) as cm:
            inputs.load_yaml_file(bad, "x")
        self.assertNotIsInstance(cm.exception, inputs.UnsafeInput)
        nonmap = self.tmp / "list.yaml"
        nonmap.write_text("- a\n- b\n")
        with self.assertRaises(BtError) as cm:
            inputs.load_yaml_file(nonmap, "x")
        self.assertNotIsInstance(cm.exception, inputs.UnsafeInput)
        big = self.tmp / "big.yaml"
        big.write_text("k: " + "x" * 70000)
        with self.assertRaises(inputs.UnsafeInput):
            inputs.load_yaml_file(big, "x")
        deep = self.tmp / "deep.yaml"
        deep.write_text("k: " + "[" * 40 + "]" * 40)
        with self.assertRaises(inputs.UnsafeInput):
            inputs.load_yaml_file(deep, "x")
        ok = self.tmp / "ok.yaml"
        ok.write_text("k: v\n")
        self.assertEqual(inputs.load_yaml_file(ok, "x"), {"k": "v"})

    def test_normal_draft_still_loads_and_gates(self):
        case_id, _ = self.make_case()
        proc, out = self.gate(case_id, send_draft())
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["result"], "pass")


class JsonOutputTest(BtTestCase):
    def test_case_show_with_date_mapping_key_outputs_json(self):
        # A YAML 1.1 date scalar used as a mapping key loads as a
        # datetime.date; json.dumps rejects non-str keys outright, so
        # case show must stringify keys instead of tracebacking.
        case_id, case_dir = new_case(self.home)
        (case_dir / "brief.yaml").write_text(
            "pack: bills\nmode: act\ndirection: pay\n"
            "2026-11-01: holiday\n"
        )
        proc = run_bt(self.home, "case", "show", case_id)
        self.assertNotIn("Traceback", proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(out["brief"]["2026-11-01"], "holiday")

    def test_case_show_with_date_keys_in_plan_and_nested(self):
        case_id, case_dir = new_case(self.home)
        (case_dir / "plan.yaml").write_text(
            "target: 1000\nmilestones:\n  2026-06-30: mid\n"
        )
        proc = run_bt(self.home, "case", "show", case_id)
        self.assertNotIn("Traceback", proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(out["plan"]["milestones"]["2026-06-30"], "mid")


class HostileScalarTest(HardenedCase):
    HUGE = 10 ** 4300  # one digit past the int-to-str limit

    def test_huge_int_action_blocks(self):
        _, case_dir = self.make_case()
        draft = {
            "action": self.HUGE, "offer": 1100, "period": "once",
            "template": "hi", "claims": [],
        }
        result, reasons, rendered = gate.check(case_dir, draft)
        self.assertEqual(result, "block")
        self.assertIn("not one of", " ".join(reasons))
        self.assertIsNone(rendered)

    def test_huge_int_claim_id_blocks(self):
        _, case_dir = self.make_case()
        draft = {
            "action": "send", "offer": 1100, "period": "once",
            "template": "hi", "claims": [self.HUGE],
        }
        result, reasons, _ = gate.check(case_dir, draft)
        self.assertEqual(result, "block")
        self.assertIn("not in plan facts", " ".join(reasons))

    def test_huge_int_unknown_key_blocks(self):
        _, case_dir = self.make_case()
        draft = {
            self.HUGE: "x", "action": "send", "offer": 1100,
            "period": "once", "template": "hi", "claims": [],
        }
        result, reasons, _ = gate.check(case_dir, draft)
        self.assertEqual(result, "block")
        self.assertIn("unknown draft keys", " ".join(reasons))

    def test_long_string_ids_still_match_plan_facts(self):
        # A long but valid claim id must still match, not truncate to
        # a display form: the reason path is for ids that miss.
        _, case_dir = self.make_case()
        fid = "f" * 60
        plan = dict(PLAN_BILLS)
        plan["facts"] = [{"id": fid, "text": "x", "source": "s"}]
        write_case_files(case_dir, plan=plan)
        draft = send_draft(template="see {fact:" + fid + "}")
        result, reasons, _ = gate.check(case_dir, draft)
        self.assertNotIn("not in plan facts", " ".join(reasons))

    def test_non_short_string_values_block_through_bt(self):
        # Through bt.py: a list, map or oversized scalar where a short
        # string belongs is a block, never an exit-2 error.
        case_id, _ = self.make_case()
        for draft in (
            send_draft(action=["send"]),
            send_draft(action={"do": "send"}),
            send_draft(action="x" * 5000),
            send_draft(claims=[["nested"]]),
            send_draft(claims=[{"a": 1}]),
            send_draft(claims=["c" * 5000]),
        ):
            with self.subTest(draft=str(draft)[:80]):
                proc, out = self.gate(case_id, draft)
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["result"], "block")


class BlockReasonTest(HardenedCase):
    def test_block_reports_only_the_generic_limit_reason(self):
        # Floor 1200/month; a 1200/year send offer repeats the floor's
        # digits while a worse-than-floor option value blocks. On the
        # block the digits reason would leak one bit about the floor:
        # 1200/year and 1201/year must report identical reasons (0007).
        plan = dict(
            PLAN_BILLS,
            period="month",
            options=[
                {"label": "annual", "value": 15000,
                 "period": "year", "terms": "prepay"}
            ],
            facts=[],
        )
        case_id, _ = self.make_case(plan=plan)
        outs = []
        for offer in (1200, 1201):
            proc, out = self.gate(
                case_id,
                send_draft(
                    offer=offer, period="year",
                    template="I can do {offer} plus {option:annual}",
                ),
            )
            self.assertEqual(proc.returncode, 1, out)
            self.assertEqual(out["result"], "block")
            outs.append(out["reasons"])
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[0], [LIMITS])

    def test_converted_limit_reason_also_drops_on_block(self):
        # Same oracle on the other floor-adjacent reason: a quote that
        # equals the floor x12 routes as "converted limit" on review
        # but must not appear once the draft blocks.
        plan = dict(
            PLAN_BILLS,
            period="month",
            options=[
                {"label": "annual", "value": 15000,
                 "period": "year", "terms": "prepay"}
            ],
            facts=[],
        )
        case_id, _ = self.make_case(plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(
                period="month",
                template="you said {quote:1}; we offer {option:annual}",
            ),
            inbound={"offer": None, "text": "x", "amounts": [14400]},
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertEqual(out["reasons"], [LIMITS])


if __name__ == "__main__":
    unittest.main()
