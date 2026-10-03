#!/usr/bin/env python3
"""betterterms runtime tool. Owns case files, the floor, the gate, the
scorer and the ledger. Every subcommand prints one JSON object to
stdout.

  bt.py case new --pack <pack> [--mode act|coach] [--direction pay|receive]
  bt.py case set-floor <case_id>     (hidden getpass prompt on a TTY, else stdin, never argv)
  bt.py case show <case_id>
  bt.py gate <case_id> --draft <draft.yaml> [--approved] [--inbound <inbound.yaml>]
  bt.py score <case_id> --inbound <inbound.yaml>
  bt.py ledger add <case_id> --before N --after N --period month|year
  bt.py ledger total

Exit codes: 0 ok/pass, 1 block, 2 usage or error, 3 needs approval.
"""

import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from btlib import BtError, cases, gate, ledger, score, yaml


def _load_yaml_file(path, what):
    p = Path(path)
    if not p.is_file():
        raise BtError(f"{what} file not found: {path}")
    try:
        data = yaml.load(p.read_text(encoding="utf-8"))
    except yaml.Error as e:
        raise BtError(f"{what}: {e}")
    if not isinstance(data, dict):
        raise BtError(f"{what}: expected a mapping")
    return data


def cmd_case_new(args):
    case_id, d = cases.create_case(args.pack, args.mode, args.direction)
    return 0, {"case_id": case_id, "path": str(d)}


def cmd_case_set_floor(args):
    d = cases.require_case(args.case_id)
    if sys.stdin.isatty():
        raw = getpass.getpass("Walk-away number (hidden): ")
    else:
        raw = sys.stdin.read()
    cases.set_floor(d, raw)
    return 0, {"ok": True}


def cmd_case_show(args):
    d = cases.require_case(args.case_id)
    brief_path, plan_path = d / "brief.yaml", d / "plan.yaml"
    return 0, {
        "case_id": args.case_id,
        "brief": cases.load_brief(d) if brief_path.is_file() else None,
        "plan": cases.load_plan(d) if plan_path.is_file() else None,
    }


def cmd_gate(args):
    d = cases.require_case(args.case_id)
    draft = _load_yaml_file(args.draft, "draft")
    inbound = _load_yaml_file(args.inbound, "inbound") if args.inbound else None
    result, reasons, rendered = gate.check(d, draft, approved=args.approved, inbound=inbound)
    return {"pass": 0, "block": 1, "needs_approval": 3}[result], {
        "result": result,
        "reasons": reasons,
        "rendered": rendered,
    }


def cmd_score(args):
    d = cases.require_case(args.case_id)
    inbound = _load_yaml_file(args.inbound, "inbound")
    return 0, score.classify(d, inbound)


def cmd_ledger_add(args):
    d = cases.require_case(args.case_id)
    saved = ledger.add(d, args.before, args.after, args.period)
    return 0, {"saved_per_year": saved}


def cmd_ledger_total(args):
    return 0, ledger.total()


def build_parser():
    parser = argparse.ArgumentParser(prog="bt.py", description="betterterms runtime tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_case = sub.add_parser("case", help="manage case files")
    case_sub = p_case.add_subparsers(dest="case_command", required=True)

    p_new = case_sub.add_parser("new", help="create a case")
    p_new.add_argument("--pack", required=True)
    p_new.add_argument("--mode", choices=["act", "coach"], default="act")
    p_new.add_argument("--direction", choices=["pay", "receive"], default="pay")
    p_new.set_defaults(fn=cmd_case_new)

    p_floor = case_sub.add_parser("set-floor", help="set the floor (hidden getpass prompt on a TTY, else stdin; never argv)")
    p_floor.add_argument("case_id")
    p_floor.set_defaults(fn=cmd_case_set_floor)

    p_show = case_sub.add_parser("show", help="print brief and plan (never the floor)")
    p_show.add_argument("case_id")
    p_show.set_defaults(fn=cmd_case_show)

    p_gate = sub.add_parser("gate", help="pre-send gate for a draft")
    p_gate.add_argument("case_id")
    p_gate.add_argument("--draft", required=True, help="path to draft.yaml")
    p_gate.add_argument("--approved", action="store_true")
    p_gate.add_argument("--inbound", help="path to inbound.yaml this draft answers; {quote:n} placeholders, the offer period and accept checks read it")
    p_gate.set_defaults(fn=cmd_gate)

    p_score = sub.add_parser("score", help="score an inbound message")
    p_score.add_argument("case_id")
    p_score.add_argument("--inbound", required=True, help="path to inbound.yaml")
    p_score.set_defaults(fn=cmd_score)

    p_ledger = sub.add_parser("ledger", help="savings ledger")
    ledger_sub = p_ledger.add_subparsers(dest="ledger_command", required=True)

    p_add = ledger_sub.add_parser("add", help="record a closed case")
    p_add.add_argument("case_id")
    p_add.add_argument("--before", required=True, type=float)
    p_add.add_argument("--after", required=True, type=float)
    p_add.add_argument("--period", required=True, choices=["month", "year"])
    p_add.set_defaults(fn=cmd_ledger_add)

    p_total = ledger_sub.add_parser("total", help="total savings")
    p_total.set_defaults(fn=cmd_ledger_total)

    return parser


def main(argv):
    args = build_parser().parse_args(argv)
    try:
        code, out = args.fn(args)
    except (BtError, OSError, ValueError) as e:
        code, out = 2, {"error": str(e)}
    except Exception as e:  # never a traceback; JSON or nothing
        code, out = 2, {"error": f"unexpected {type(e).__name__}: {e}"}
    print(json.dumps(out, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
