"""Shared helpers for bt.py tests. Every test uses a temp BETTERTERMS_HOME."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BT_DIR = REPO / "skills" / "betterterms-guardrails" / "scripts"
BT = BT_DIR / "bt.py"

sys.path.insert(0, str(BT_DIR))

from btlib import yaml  # noqa: E402


def run_bt(home, *args, stdin=None):
    env = dict(os.environ, BETTERTERMS_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(BT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def run_bt_json(home, *args, stdin=None):
    proc = run_bt(home, *args, stdin=stdin)
    try:
        return proc, json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"bt.py {' '.join(args)} did not print JSON\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )


def approve_held(home, case_id, args):
    """Run the gate once on ``args`` to hold the draft, record the user
    approval with ``held approve`` on the reported ``hash``, and return
    ``args`` with ``--approved`` appended so the caller's real call
    consumes it. A gate result without a hash adds nothing."""
    h = run_bt_json(home, *args)[1].get("hash")
    if h:
        proc, _ = run_bt_json(home, "held", "approve", case_id, h[:8])
        assert proc.returncode == 0, proc.stdout + proc.stderr
    return [*args, "--approved"]


def new_case(home, pack="bills", mode="act", direction="pay"):
    proc, out = run_bt_json(
        home, "case", "new", "--pack", pack, "--mode", mode, "--direction", direction
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out["case_id"], Path(out["path"])


def write_case_files(case_dir, brief=None, plan=None, floor=None):
    if brief is not None:
        (case_dir / "brief.yaml").write_text(yaml.dump(brief))
    if plan is not None:
        (case_dir / "plan.yaml").write_text(yaml.dump(plan))
    if floor is not None:
        (case_dir / ".floor").write_text(str(floor))


def write_draft(tmpdir, draft):
    path = Path(tmpdir) / "draft.yaml"
    path.write_text(yaml.dump(draft))
    return path


def send_draft(template="hi", **kw):
    """A well-formed send draft under the structured-amounts contract.
    ``offer`` defaults to 1100 (inside the band for a pay floor of
    1200); any key may be overridden or removed with ``key=None``."""
    d = {"action": "send", "offer": 1100, "period": "once",
         "template": template, "claims": []}
    d.update(kw)
    return d


def inbound_msg(offer=None, text="", amounts=None):
    """An inbound.yaml mapping: counterparty text, the extracted
    ``amounts`` list, and an optional numeric offer."""
    return {"offer": offer, "text": text,
            "amounts": [] if amounts is None else amounts}


BRIEF_PAY = {
    "pack": "bills",
    "mode": "act",
    "direction": "pay",
    "goals": ["lower bill"],
    "priorities": ["price", "terms"],
    "ranking_check": {"passed": True, "samples": []},
    "autonomy": 2,
    "never_disclose": ["acct-7788"],
    "deadline": None,
}

PLAN_BILLS = {
    "target": 1000,
    "currency": "USD",
    "options": [
        {"label": "annual", "value": 950, "terms": "12-month prepay"},
        {"label": "monthly", "value": 1100, "terms": "cancel anytime"},
    ],
    "ladder": [
        {"value": 1000, "reason": "target"},
        {"value": 1150, "reason": "fallback if pushed"},
    ],
    "patience": {"rounds": 3, "days": 14},
    "timing": "before renewal",
    "channel": "email",
    "facts": [
        {"id": "f1", "text": "competitor charges $89 per month", "source": "https://example.com/pricing"},
        {"id": "f2", "text": "policy allows retention offers", "source": "https://example.com/policy"},
    ],
}


_KEEP = object()


def plan_for(direction, floor, target=_KEEP):
    """A plan whose target, option and ladder values sit inside the
    band for the given direction and floor, so the plan-vs-limits check
    does not trip. PLAN_BILLS is shaped for a pay floor of 1200; other
    setups derive values from the floor. ``target`` overrides the plan
    target, including to None."""
    if floor is None:
        return dict(PLAN_BILLS)
    if direction == "receive":
        plan = dict(
            PLAN_BILLS,
            target=floor + 10000,
            options=[{"label": "a", "value": floor + 5000, "terms": "x"}],
            ladder=[{"value": floor + 2000, "reason": "r"}],
        )
    elif floor == 1200:
        plan = dict(PLAN_BILLS)
    else:
        plan = dict(
            PLAN_BILLS,
            options=[{"label": "a", "value": floor - 5, "terms": "x"}],
            ladder=[{"value": floor - 2, "reason": "r"}],
        )
    if target is not _KEEP:
        plan["target"] = target
    return plan


class BtTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "bthome"
        self.tmp = Path(self._tmp.name)


class PriceCase(BtTestCase):
    """A pay case with a floor, shared by the period and rendered-value
    tests: ``gate`` runs ``bt.py gate`` and ``score`` runs
    ``bt.py score`` against it."""

    def make_case(self, direction="pay", floor=100, plan=None, brief=None):
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
        return case_id

    def gate(self, case_id, draft, approved=False, inbound=None):
        path = write_draft(self.tmp, draft)
        args = ["gate", case_id, "--draft", str(path)]
        if inbound is not None:
            ipath = self.tmp / "inbound.yaml"
            ipath.write_text(yaml.dump(inbound))
            args += ["--inbound", str(ipath)]
        if approved:
            args = approve_held(self.home, case_id, args)
        return run_bt_json(self.home, *args)

    def score(self, case_id, inbound):
        ipath = self.tmp / "inbound.yaml"
        ipath.write_text(yaml.dump(inbound))
        return run_bt_json(
            self.home, "score", case_id, "--inbound", str(ipath)
        )
