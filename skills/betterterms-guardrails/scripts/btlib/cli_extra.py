"""The smaller subcommands, kept out of bt.py: ``where``, ``config
show|set``, ``case set-terms``, ``held
list|approve|reject|drop``, and ``widget
cases|approval|terms|savings``. Each command function returns
``(exit_code, dict)`` like the ones in bt.py.
"""

import math
import re
from pathlib import Path

from . import (
    MAX_AMOUNT,
    PERIODS,
    BtError,
    cases,
    config,
    held,
    widgets,
    worse_than_floor,
    yaml,
)


def cmd_where(_args):
    return 0, {
        "bt": str(Path(__file__).resolve().parents[1] / "bt.py")
    }


def cmd_config_show(_args):
    return 0, {"config": config.load()}


def cmd_config_set(args):
    return 0, {"config": config.set_value(args.key, args.value)}


_INT = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")
_DECIMAL = re.compile(r"\.\d{1,2}")


def parse_amount(raw):
    """A user-typed amount: ``62``, ``62.50``, ``$62`` or ``1,200``.
    Anything else raises BtError with a plain message."""
    s = str(raw or "").strip()
    if s.startswith("$"):
        s = s[1:].strip()
    integer, dot, decimals = s.partition(".")
    if not _INT.fullmatch(integer) or (
        dot and not _DECIMAL.fullmatch(dot + decimals)
    ):
        raise BtError(
            f"bad amount {raw!r}; use a number like 62 or 62.50"
        )
    value = float(s.replace(",", ""))
    if (
        not math.isfinite(value)
        or value <= 0
        or value > MAX_AMOUNT
    ):
        raise BtError(
            f"bad amount {raw!r}; use a number like 62 or 62.50"
        )
    return value


def _money(raw):
    v = parse_amount(raw)
    return int(v) if float(v).is_integer() else v


def cmd_case_set_terms(args):
    """Write ``target`` and ``best_alternative`` into plan.yaml
    (spec 6.4). When a floor exists the target is checked against it
    first (the same plan-limits comparison the gate runs, read in the
    floor's period): a target on the wrong side of the walk-away
    refuses with nothing saved, since the plan would then conflict
    with the user's limits on every later gate call. The command
    reads ``.floor`` for that check but never writes or echoes it."""
    d = cases.require_case(args.case_id)
    plan = cases.load_plan(d)
    touched = False
    if args.target is not None:
        target = _money(args.target)
        floor = cases.read_floor(d)
        if floor is not None and worse_than_floor(
            target,
            floor,
            cases.direction_of(cases.load_brief(d)),
        ):
            raise BtError(
                "target is on the wrong side of your walk-away; "
                "nothing saved"
            )
        plan["target"] = target
        touched = True
    if any(
        v is not None for v in (args.alternative, args.period, args.note)
    ):
        alt = plan.get("best_alternative")
        if alt is None:
            alt = {}
        if not isinstance(alt, dict):
            raise BtError("best_alternative must be a mapping")
        if args.alternative is not None:
            alt["amount"] = _money(args.alternative)
        if args.period is not None:
            p = str(args.period).lower()
            if p not in PERIODS:
                raise BtError("period must be once, month or year")
            alt["period"] = p
        if args.note is not None:
            alt["note"] = args.note
        plan["best_alternative"] = alt
        touched = True
    if not touched:
        raise BtError(
            "nothing to set; pass --target, --alternative, "
            "--period or --note"
        )
    held.atomic_write(d / "plan.yaml", yaml.dump(plan))
    return 0, {"ok": True, "plan": plan}


def cmd_held_list(args):
    d = cases.require_case(args.case_id)
    return 0, {"held": held.list_held(d)}


def cmd_held_approve(args):
    d = cases.require_case(args.case_id)
    h = held.approve(d, args.hash8)
    return 0, {"ok": True, "hash": h}


def cmd_held_reject(args):
    d = cases.require_case(args.case_id)
    h = held.reject(d, args.hash8)
    return 0, {"ok": True, "hash": h}


def cmd_held_drop(args):
    d = cases.require_case(args.case_id)
    h = held.drop(d, args.hash8)
    return 0, {"ok": True, "hash": h}


def cmd_widget_cases(_args):
    return 0, {"html": widgets.cases_widget()}


def cmd_widget_approval(args):
    d = cases.require_case(args.case_id)
    return 0, {"html": widgets.approval_widget(d, args.case_id, args.hash8)}


def cmd_widget_terms(args):
    d = cases.require_case(args.case_id)
    return 0, {"html": widgets.terms_widget(d, args.case_id)}


def cmd_widget_savings(_args):
    return 0, {"html": widgets.savings_widget()}


def register(sub, case_sub):
    p_where = sub.add_parser(
        "where", help="print the absolute path of this bt.py"
    )
    p_where.set_defaults(fn=cmd_where)

    p_config = sub.add_parser(
        "config", help="user defaults for new cases"
    )
    config_sub = p_config.add_subparsers(
        dest="config_command", required=True
    )
    p_show = config_sub.add_parser(
        "show", help="print the merged config"
    )
    p_show.set_defaults(fn=cmd_config_show)
    p_set = config_sub.add_parser("set", help="set a config key")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.set_defaults(fn=cmd_config_set)

    p_terms = case_sub.add_parser(
        "set-terms",
        help="write target and best alternative to plan.yaml",
    )
    p_terms.add_argument("case_id")
    p_terms.add_argument("--target")
    p_terms.add_argument("--alternative")
    p_terms.add_argument("--period")
    p_terms.add_argument("--note")
    p_terms.set_defaults(fn=cmd_case_set_terms)

    p_held = sub.add_parser(
        "held", help="held drafts and approvals"
    )
    held_sub = p_held.add_subparsers(
        dest="held_command", required=True
    )
    p_list = held_sub.add_parser(
        "list", help="list held drafts, oldest first"
    )
    p_list.add_argument("case_id")
    p_list.set_defaults(fn=cmd_held_list)
    p_app = held_sub.add_parser(
        "approve", help="approve a held draft by hash prefix"
    )
    p_app.add_argument("case_id")
    p_app.add_argument("hash8")
    p_app.set_defaults(fn=cmd_held_approve)
    p_rej = held_sub.add_parser(
        "reject", help="reject and drop a held draft"
    )
    p_rej.add_argument("case_id")
    p_rej.add_argument("hash8")
    p_rej.set_defaults(fn=cmd_held_reject)
    p_drop = held_sub.add_parser(
        "drop", help="drop a held draft quietly (no thread.md marker)"
    )
    p_drop.add_argument("case_id")
    p_drop.add_argument("hash8")
    p_drop.set_defaults(fn=cmd_held_drop)

    p_widget = sub.add_parser(
        "widget",
        help="HTML widget fragments for cloud threads (spec 6.8)",
    )
    widget_sub = p_widget.add_subparsers(
        dest="widget_command", required=True
    )
    p_wcases = widget_sub.add_parser(
        "cases", help="every case as one widget"
    )
    p_wcases.set_defaults(fn=cmd_widget_cases)
    p_wapp = widget_sub.add_parser(
        "approval", help="one held draft as an approval card"
    )
    p_wapp.add_argument("case_id")
    p_wapp.add_argument("hash8")
    p_wapp.set_defaults(fn=cmd_widget_approval)
    p_wterms = widget_sub.add_parser(
        "terms", help="the terms editor as a widget"
    )
    p_wterms.add_argument("case_id")
    p_wterms.set_defaults(fn=cmd_widget_terms)
    p_wsave = widget_sub.add_parser(
        "savings", help="the savings view as a widget"
    )
    p_wsave.set_defaults(fn=cmd_widget_savings)
