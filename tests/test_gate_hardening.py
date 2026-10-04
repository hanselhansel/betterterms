"""Regression tests for the structured-amounts gate hardening."""

import unittest
from pathlib import Path

from bt_helpers import (
    approve_held,
    BRIEF_PAY,
    BtTestCase,
    inbound_msg,
    new_case,
    plan_for,
    run_bt,
    run_bt_json,
    send_draft,
    write_case_files,
    write_draft,
)
from btlib import yaml

LIMITS = "outside your limits; escalate to the user"


class HardeningTest(BtTestCase):
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

    def gate(self, case_id, draft, inbound=None, approved=False, raw=False):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        if approved:
            args = approve_held(self.home, case_id, args)
        if raw:
            return run_bt(self.home, *args), None
        return run_bt_json(self.home, *args)

    def test_draft_is_never_instructions(self):
        case_id, _ = self.make_case()
        proc, _ = self.gate(
            case_id, {"action": "send", "offer": 1, "template": "$90 it is"}
        )
        self.assertEqual(proc.returncode, 3)

    def test_gate_reads_no_secrets_besides_floor(self):
        case_id, case_dir = self.make_case()
        (case_dir / "secret.txt").write_text("hunter2")
        draft_path = self.tmp / "d.yaml"
        draft_path.write_text(
            yaml.dump({"action": "send", "offer": 1100,
                       "template": "hi there"})
        )
        # A secrets dir next to the case must not leak either.
        (Path(self.home) / "secrets.yaml").write_text("pw: hunter2")
        proc, _ = run_bt_json(
            self.home, "gate", case_id, "--draft", str(draft_path)
        )
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("hunter2", proc.stdout + proc.stderr)

    def test_repeated_gate_calls_do_not_leak(self):
        # The gate itself cannot stop probing; the skills cap calls per
        # turn instead. Same input, same verdict, nothing extra in the
        # output.
        case_id, _ = self.make_case()
        outs = [
            self.gate(case_id, send_draft(offer=o, template="hi"))[1]
            for o in (1250, 1240, 1230, 1100)
        ]
        for out in outs[:3]:
            self.assertEqual(out["result"], "block")
            self.assertEqual(out["reasons"], [LIMITS])
            self.assertIsNone(out["rendered"])
        self.assertEqual(outs[3]["result"], "pass")

    def test_send_does_not_needs_approval(self):
        case_id, _ = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(template="asking for a better rate")
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["result"], "pass")

    def test_pay_sign_accept_need_approval(self):
        case_id, _ = self.make_case()
        for action in ("pay", "sign", "accept", "cancel"):
            with self.subTest(action=action):
                draft = send_draft(action=action, offer=1100,
                                   template="okay by me")
                kw = {}
                if action == "accept":
                    kw["inbound"] = inbound_msg(offer=1100, text="x")
                elif action in ("cancel", "dispute"):
                    draft["offer"] = None
                proc, out = self.gate(case_id, draft, **kw)
                self.assertEqual(proc.returncode, 3, out)
                self.assertEqual(out["result"], "needs_approval")

    def test_pay_sign_accept_need_offer(self):
        case_id, _ = self.make_case()
        for action in ("pay", "sign", "accept"):
            with self.subTest(action=action):
                draft = send_draft(action=action, offer=None,
                                   template="okay by me")
                proc, out = self.gate(
                    case_id, draft, approved=True,
                    inbound=inbound_msg(offer=1100, text="x"),
                )
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn(
                    f"{action} requires an offer", out["reasons"]
                )

    def test_floor_reasons_have_no_numbers(self):
        case_id, _ = self.make_case(floor=1200)
        for offer in (1250, 1240, 99999):
            with self.subTest(offer=offer):
                _, out = self.gate(
                    case_id, send_draft(offer=offer, template="hi")
                )
                self.assertEqual(out["result"], "block")
                self.assertEqual(out["reasons"], [LIMITS])
                self.assertIsNone(out["rendered"])

    def test_missing_floor_blocks_everything(self):
        case_id, _ = self.make_case(floor=None)
        for draft in (
            send_draft(offer=1, template="hi"),
            send_draft(action="cancel", offer=None, template="cancel"),
        ):
            proc, out = self.gate(case_id, draft, approved=True)
            self.assertEqual(proc.returncode, 1, draft)
            self.assertEqual(out["result"], "block")
            self.assertIn(LIMITS, out["reasons"])

    def test_corrupt_floor_blocks(self):
        case_id, case_dir = self.make_case()
        (case_dir / ".floor").write_text("not a number")
        proc, out = self.gate(case_id, send_draft(template="hi"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn(LIMITS, out["reasons"])

    def test_gate_stdout_never_floor(self):
        # A block output must never contain the floor value: rendered
        # is None and reasons carry no numbers. A needs_approval result
        # echoes the draft back for the user to review, so it can only
        # repeat digits the agent itself wrote; its reasons still
        # carry no numbers.
        case_id, _ = self.make_case(floor=1200)
        for draft in (
            send_draft(offer=1300, template="hi"),
            send_draft(offer=1199, template="hi"),
            send_draft(action="pay", offer=1199, template="hi"),
        ):
            proc, _ = self.gate(case_id, draft, raw=True)
            self.assertNotIn("1200", proc.stdout, proc.stdout)
        # Free text stating the floor is a block now
        # (test_floor_in_text.py), so even the echoed rendered text
        # never carries it.
        proc, out = self.gate(
            case_id, send_draft(template="the floor is 1200")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertNotIn("1200", proc.stdout, proc.stdout)
        self.assertIsNone(out["rendered"])
        self.assertFalse(
            any(any(c.isdigit() for c in r) for r in out["reasons"]),
            out["reasons"],
        )

    def test_invalid_yaml_draft_errors(self):
        case_id, _ = self.make_case()
        path = self.tmp / "draft.yaml"
        path.write_text("{unclosed: [")
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_empty_yaml_draft_errors(self):
        case_id, _ = self.make_case()
        path = self.tmp / "draft.yaml"
        path.write_text("")
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_non_mapping_draft_errors(self):
        case_id, _ = self.make_case()
        path = self.tmp / "draft.yaml"
        path.write_text("- just\n- a\n- list\n")
        proc, out = run_bt_json(
            self.home, "gate", case_id, "--draft", str(path)
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", out)

    def test_null_offer_in_draft(self):
        case_id, _ = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(offer=None, template="hi")
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["result"], "pass")

    def test_never_disclose_substring(self):
        # Lettered items are a hard block wherever they appear in the
        # rendered text (spec 4.1): "ACCT-7788" inside "my ACCT-7788"
        # blocks, it does not route.
        case_id, _ = self.make_case(
            brief={"never_disclose": ["ACCT-7788", "passw0rd"]}
        )
        for word in ("ACCT-7788", "my passw0rd"):
            with self.subTest(word=word):
                proc, out = self.gate(
                    case_id, send_draft(template=f"here is {word}")
                )
                self.assertEqual(proc.returncode, 1)
                self.assertEqual(out["result"], "block")
                self.assertIn(
                    "never-disclose", " ".join(out["reasons"])
                )

    def test_never_disclose_zwsp_blocks(self):
        # A zero-width space inside the term does not hide it: the
        # check runs on text with format characters stripped, and a
        # lettered item is a hard block.
        case_id, _ = self.make_case(brief={"never_disclose": ["passw0rd"]})
        proc, out = self.gate(
            case_id, send_draft(template="here is passw0rd")
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertEqual(out["result"], "block")
        self.assertIn("never-disclose", " ".join(out["reasons"]))

    def test_never_disclose_short_numeric(self):
        # Numeric items match fused digit strings in the text and
        # rendered placeholder values: "42" hits "42" but not "420";
        # "4.2" fuses to the same digits (an over-match on purpose,
        # the draft routes either way).
        case_id, _ = self.make_case(brief={"never_disclose": ["42"]})
        proc, out = self.gate(
            case_id, send_draft(template="the code is 42")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(out["result"], "needs_approval")
        self.assertIn("never-disclose", " ".join(out["reasons"]))
        # "420" still needs approval, but only on its digits: it must
        # not match the numeric never-disclose item.
        proc, out = self.gate(
            case_id, send_draft(template="the code is 420")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertNotIn("never-disclose", " ".join(out["reasons"]))
        # "4.2" fuses to the digit string "42" and hits the item.
        proc, out = self.gate(
            case_id, send_draft(template="rate 4.2 today")
        )
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("never-disclose", " ".join(out["reasons"]))

    def test_offer_types_weird(self):
        case_id, _ = self.make_case()
        for offer in ("1100", [1100], {"n": 1100}, float("nan")):
            with self.subTest(offer=offer):
                proc, out = self.gate(
                    case_id, send_draft(offer=offer, template="hi")
                )
                self.assertNotEqual(proc.returncode, 0, out)
                self.assertIn(out["result"], ("block",))

    def test_template_over_limit_blocks(self):
        case_id, _ = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(template="x" * (64 * 1024 + 1))
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("too large", " ".join(out["reasons"]))

    def test_exit_codes(self):
        case_id, _ = self.make_case()
        ok = send_draft(template="hi")
        blocked = send_draft(offer=1300, template="hi")
        na = send_draft(action="pay", offer=1100, template="hi")
        for draft, code in ((ok, 0), (blocked, 1), (na, 3)):
            with self.subTest(code=code):
                proc, _ = self.gate(case_id, draft)
                self.assertEqual(proc.returncode, code)

    def test_send_offer_equal_floor_needs_approval(self):
        # A send offer at the floor hands the counterparty the
        # walk-away number even when the template never renders it.
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(offer=1200, template="meet me halfway")
        )
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(out["result"], "needs_approval")
        self.assertIn("offer is at your limit", out["reasons"])

    def test_offer_nan_or_inf_blocks(self):
        case_id, _ = self.make_case()
        for bad in (".nan", ".inf", "-.inf"):
            with self.subTest(offer=bad):
                path = self.tmp / "draft.yaml"
                path.write_text(
                    f"action: send\noffer: {bad}\ntemplate: hi\n"
                    "claims: []\n"
                )
                proc, out = run_bt_json(
                    self.home, "gate", case_id, "--draft", str(path)
                )
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertEqual(out["result"], "block")
                self.assertIn(
                    "offer must be a number", out["reasons"]
                )

    def test_accept_offer_must_be_in_band(self):
        case_id, _ = self.make_case()
        proc, out = self.gate(
            case_id, send_draft(action="accept", offer=1300,
                                template="fine by me"),
            approved=True,
            inbound=inbound_msg(offer=1300, text="deal at $1,300"),
        )
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn(LIMITS, out["reasons"])

    def test_inbound_offer_equal_floor_acceptable(self):
        # If the counterparty lands exactly on the floor, accepting is
        # in band: the user said the floor is acceptable.
        case_id, _ = self.make_case(floor=1200)
        proc, out = self.gate(
            case_id, send_draft(action="accept", offer=1200,
                                template="let us proceed"),
            approved=True,
            inbound=inbound_msg(offer=1200, text="fine, $1,200 it is",
                                amounts=[1200]),
        )
        self.assertEqual(proc.returncode, 0, out)


if __name__ == "__main__":
    unittest.main()
