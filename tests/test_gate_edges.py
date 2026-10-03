"""Gate edge cases: verdict precedence, action validation and YAML or
case-file shape errors under the structured-amounts contract."""

import unittest

from bt_helpers import (
    BRIEF_PAY,
    PLAN_BILLS,
    BtTestCase,
    new_case,
    plan_for,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import yaml

LIMITS = "outside your limits; escalate to the user"


class GateEdgeTest(BtTestCase):
    def make_case(self, direction="pay", floor=1200, plan=None):
        case_id, case_dir = new_case(self.home, direction=direction)
        write_case_files(
            case_dir,
            brief=dict(BRIEF_PAY, direction=direction),
            plan=plan_for(direction, floor) if plan is None else plan,
            floor=floor,
        )
        return case_id

    def gate(self, case_id, draft, approved=False, inbound_path=None):
        args = ["gate", case_id, "--draft", str(write_draft(self.tmp, draft))]
        if approved:
            args.append("--approved")
        if inbound_path is not None:
            args += ["--inbound", str(inbound_path)]
        return run_bt_json(self.home, *args)

    def test_block_dominates_and_bad_actions_block(self):
        case_id = self.make_case(floor=1200)
        rows = [
            (send_draft(action="accept", offer=1300, template="deal"),
             False, LIMITS),
            (send_draft(action="accept", offer=1300, template="deal"),
             True, LIMITS),
            ({"offer": 1100, "template": "hello", "claims": []},
             False, "not one of"),
            (send_draft(action="Send", template="hello"),
             False, "not one of"),
            (send_draft(action="wire", template="hello"),
             True, "not one of"),
        ]
        for draft, approved, fragment in rows:
            with self.subTest(draft=draft, approved=approved):
                proc, out = self.gate(case_id, draft, approved)
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["result"], "block")
                self.assertIn(fragment, " ".join(out["reasons"]))

    def test_target_placeholder_renders_large_value(self):
        # The plan target renders through {target}; a seven-figure value
        # is formatted with separators.
        plan = dict(PLAN_BILLS, target=1200000, options=[], ladder=[],
                    facts=[])
        case_id = self.make_case(direction="receive", floor=1100000,
                                 plan=plan)
        proc, out = self.gate(
            case_id,
            send_draft(offer=1200000, template="we can close at {target}"),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "we can close at $1,200,000")

    def test_offer_that_is_not_a_number_blocks(self):
        case_id = self.make_case(floor=1200)
        bad_offers = ("$1,250", "about 1200", "1200", [1200], True,
                      {"x": 1})
        for offer in bad_offers:
            with self.subTest(offer=offer):
                proc, out = self.gate(
                    case_id, send_draft(offer=offer, template="counter"),
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertEqual(out["result"], "block")
                self.assertIn("offer must be a number", out["reasons"])
        proc, out = self.gate(
            case_id, send_draft(offer=None, template="counter"),
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["reasons"], [])

    def test_malformed_or_non_mapping_draft_and_inbound_error(self):
        case_id = self.make_case(floor=1200)
        good = self.tmp / "good.yaml"
        good.write_text(
            "action: send\noffer: 1100\ntemplate: hi\nclaims: []\n"
        )
        bad = self.tmp / "bad.yaml"
        bad.write_text("offer: [unclosed\n")
        lst = self.tmp / "list.yaml"
        lst.write_text("- action\n- send\n")
        rows = [(bad, None), (lst, None), (good, bad), (good, lst)]
        for draft_path, inbound_path in rows:
            with self.subTest(draft=draft_path.name,
                              inbound=inbound_path):
                args = ["gate", case_id, "--draft", str(draft_path)]
                if inbound_path is not None:
                    args += ["--inbound", str(inbound_path)]
                proc, out = run_bt_json(self.home, *args)
                self.assertEqual(proc.returncode, 2, out)
                self.assertIn("error", out)

    def test_corrupt_case_files_error(self):
        case_id, case_dir = new_case(self.home, direction="pay")
        write_case_files(
            case_dir, brief=dict(BRIEF_PAY), plan=PLAN_BILLS, floor=1200,
        )
        draft = write_draft(
            self.tmp,
            {"action": "send", "offer": 1100, "template": "hi",
             "claims": []},
        )
        inbound = self.tmp / "inbound.yaml"
        inbound.write_text("offer: 1100\ntext: counter\n")
        originals = {
            name: (case_dir / name).read_text()
            for name in ("brief.yaml", "plan.yaml", ".floor")
        }
        rows = [
            ("brief.yaml", "pack: [unclosed\n", 2),
            ("plan.yaml", "target: [unclosed\n", 2),
            ("brief.yaml", "- a\n- b\n", 2),
            # A corrupt .floor file is a runtime limit failure: the gate
            # blocks (exit 1) instead of trusting a guess, while the
            # scorer reports the error (exit 2).
            (".floor", "not a number\n", 1),
        ]
        for name, content, gate_rc in rows:
            with self.subTest(corrupt=f"{name}: {content.strip()}"):
                path = case_dir / name
                path.write_text(content)
                try:
                    proc, out = run_bt_json(
                        self.home, "gate", case_id, "--draft", str(draft)
                    )
                    self.assertEqual(proc.returncode, gate_rc, out)
                    if gate_rc == 1:
                        self.assertEqual(out["result"], "block")
                        self.assertIn(LIMITS, out["reasons"])
                    else:
                        self.assertIn("error", out)
                    proc, out = run_bt_json(
                        self.home, "score", case_id,
                        "--inbound", str(inbound)
                    )
                    self.assertEqual(proc.returncode, 2, out)
                    self.assertIn("error", out)
                finally:
                    path.write_text(originals[name])

    def test_plan_placeholders_render_offer_options_ladder(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id,
            send_draft(
                template="I can do {offer} monthly, {option:annual} "
                "annually, or {target} long-term; pushed: {ladder:2}"
            ),
        )
        self.assertEqual(out["reasons"], [])
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(
            out["rendered"],
            "I can do $1,100 monthly, $950 annually, or $1,000 "
            "long-term; pushed: $1,150",
        )

    def test_repeated_currency_sign_reported_once(self):
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(template="not $55, I said not $55"),
        )
        self.assertEqual(proc.returncode, 3, out)
        unusual = [r for r in out["reasons"] if "unusual" in r]
        self.assertEqual(unusual, ["unusual characters in the message"])

    def test_missing_claims_and_missing_offer_default(self):
        # Absent claims and offer read as empty, not errors.
        case_id = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, {"action": "send", "template": "hi there"},
        )
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(out["rendered"], "hi there")


if __name__ == "__main__":
    unittest.main()
