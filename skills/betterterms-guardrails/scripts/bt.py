#!/usr/bin/env python3
"""betterterms runtime tool. Owns case files, the floor, the gate, the
scorer and the ledger. Every subcommand prints one JSON object to
stdout.

  bt.py where
  bt.py config show | config set <key> <value>
  bt.py case new --pack <pack> [--mode act|coach] [--direction pay|receive]
  bt.py case set-floor <case_id>     (hidden getpass prompt on a TTY, else stdin, never argv)
  bt.py case set-terms <case_id> [--target N] [--alternative N] [--period P] [--note T]
  bt.py case show <case_id>
  bt.py gate <case_id> --draft <draft.yaml> [--approved] [--inbound <inbound.yaml>]
  bt.py held list <case_id>
  bt.py held approve <case_id> <hash8>
  bt.py held reject <case_id> <hash8>
  bt.py held drop <case_id> <hash8>     (drop the record, no thread marker)
  bt.py widget cases | widget approval <case_id> <hash8> | widget terms <case_id> | widget savings
  bt.py score <case_id> --inbound <inbound.yaml>
  bt.py ledger add <case_id> --before N --after N --period once|month|year
  bt.py ledger total
  bt.py source add <case_id>         (record read as YAML from stdin)
  bt.py source list <case_id>
  bt.py source stale <case_id> [--days 90]

Exit codes: 0 ok/pass, 1 block, 2 usage or error, 3 needs approval.
"""

import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from btlib import (
    BtError, cases, cli_extra, context, floorio, gate, held, inputs,
    ledger, score, sources, worse_than_floor, yaml,
)


def _blocked_input(e):
    """A draft or inbound file refused on size or depth fails closed:
    the gate or the scorer reports a block, never a usage error."""
    return "block", [str(e)], None


def cmd_case_new(args):
    case_id, d = cases.create_case(args.pack, args.mode, args.direction)
    return 0, {"case_id": case_id, "path": str(d)}


def cmd_case_set_floor(args):
    d = cases.require_case(args.case_id)
    if sys.stdin.isatty():
        raw = getpass.getpass("Walk-away number (hidden): ")
    else:
        raw = sys.stdin.read()
    # The value parses before the conflict check so a malformed
    # walk-away reports the parse message, then a saved target checks
    # the side: a walk-away that would strand the target on its wrong
    # side refuses with nothing saved (the mirror of the set-terms
    # refusal). Neither message ever carries a number.
    value = floorio.parse_number(raw)
    target = cases.positive(cases.load_plan(d).get("target"))
    if target is not None and worse_than_floor(
        target, value, cases.direction_of(cases.load_brief(d))
    ):
        raise BtError(
            "walk-away is on the wrong side of your target; "
            "nothing saved"
        )
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
    draft = None
    try:
        draft = inputs.load_yaml_file(args.draft, "draft")
        inbound = (
            inputs.load_yaml_file(args.inbound, "inbound")
            if args.inbound
            else None
        )
    except inputs.UnsafeInput as e:
        result, reasons, rendered = _blocked_input(e)
        held.supersede(d, None)
    except Exception:
        # Any failure loading the input -- malformed file, unreadable
        # case, or an unexpected exception -- is still an intervening
        # attempt: consent retires before the error exits, and the
        # original exception propagates unchanged.
        held.supersede(d, None)
        raise
    else:
        try:
            result, reasons, rendered = gate.check(
                d, draft, approved=args.approved, inbound=inbound
            )
        except Exception:
            # An error inside the check -- a broken case file, a
            # persisted inbound.yaml the reader refuses, or any
            # unexpected failure -- still retires consent before the
            # error exits. The verdict itself never changes.
            held.supersede(d, None)
            raise
    out = {
        "result": result,
        "reasons": reasons,
        "rendered": rendered,
    }
    if result == "needs_approval" and rendered is not None:
        # Same context digest the check bound: a supplied inbound, or
        # the persisted inbound.yaml when --inbound was omitted.
        ctx = context.resolve(d, inbound)[1]
        out["hash"] = held.draft_hash(
            held.draft_record(d, draft, rendered, ctx)
        )
    # The verdict is recorded in the case folder itself so the pane
    # and widgets read the same answer the agent got, on every call
    # including refused inputs; the write is best-effort because
    # stdout carries the contract.
    try:
        held.atomic_write(d / "gate.json", json.dumps(out))
    except OSError:
        pass
    return {"pass": 0, "block": 1, "needs_approval": 3}[result], out


def cmd_score(args):
    d = cases.require_case(args.case_id)
    try:
        inbound = inputs.load_yaml_file(args.inbound, "inbound")
        return 0, score.classify(d, inbound)
    except inputs.UnsafeInput as e:
        result, reasons, rendered = _blocked_input(e)
        return 1, {
            "result": result,
            "reasons": reasons,
            "rendered": rendered,
        }


def cmd_ledger_add(args):
    d = cases.require_case(args.case_id)
    saved = ledger.add(d, args.before, args.after, args.period)
    key = "saved_once" if args.period == "once" else "saved_per_year"
    return 0, {key: saved}


def cmd_ledger_total(args):
    return 0, ledger.total()


def cmd_source_add(args):
    d = cases.require_case(args.case_id)
    try:
        data = yaml.load(sys.stdin.read())
    except yaml.Error as e:
        raise BtError(f"source record: {e}")
    source_id, path = sources.add(d, data)
    return 0, {"id": source_id, "path": str(path)}


def cmd_source_list(args):
    d = cases.require_case(args.case_id)
    return 0, {"sources": sources.list_records(d)}


def cmd_source_stale(args):
    d = cases.require_case(args.case_id)
    return 0, {"days": args.days, "stale": sources.stale(d, args.days)}


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
    p_add.add_argument("--period", required=True, choices=["once", "month", "year"])
    p_add.set_defaults(fn=cmd_ledger_add)

    p_total = ledger_sub.add_parser("total", help="total savings")
    p_total.set_defaults(fn=cmd_ledger_total)

    p_source = sub.add_parser("source", help="research source records")
    source_sub = p_source.add_subparsers(dest="source_command", required=True)

    p_sadd = source_sub.add_parser(
        "add", help="add a source record (YAML mapping on stdin)"
    )
    p_sadd.add_argument("case_id")
    p_sadd.set_defaults(fn=cmd_source_add)

    p_slist = source_sub.add_parser("list", help="list source records")
    p_slist.add_argument("case_id")
    p_slist.set_defaults(fn=cmd_source_list)

    p_sstale = source_sub.add_parser(
        "stale", help="list records older than --days"
    )
    p_sstale.add_argument("case_id")
    p_sstale.add_argument("--days", type=int, default=90)
    p_sstale.set_defaults(fn=cmd_source_stale)

    cli_extra.register(sub, case_sub)

    return parser


def _jsonable(value):
    """Coerce a parsed YAML value into JSON-safe shape: mapping keys
    stringify (a ``2026-11-01`` key loads as a datetime.date), and any
    scalar JSON cannot carry becomes ``str()``."""
    if isinstance(value, dict):
        return {
            key if isinstance(key, str) else str(key): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def main(argv):
    args = build_parser().parse_args(argv)
    try:
        code, out = args.fn(args)
        text = json.dumps(_jsonable(out), default=str)
    except (BtError, OSError, ValueError) as e:
        code, text = 2, json.dumps({"error": str(e)})
    except Exception as e:  # never a traceback; JSON or nothing
        code, text = 2, json.dumps(
            {"error": f"unexpected {type(e).__name__}: {e}"}
        )
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
