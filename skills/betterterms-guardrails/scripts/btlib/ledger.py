"""Savings ledger. One JSON line per closed case in
``$BETTERTERMS_HOME/ledger.jsonl``. ``saved_per_year`` is positive when
the outcome is better than before: ``before - after`` for ``pay`` cases,
``after - before`` for ``receive`` cases, times the periods per year,
rounded to the currency minor unit.
"""

import json
import math
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from . import BtError, MAX_AMOUNT, cases, minor

PERIODS_PER_YEAR = {"month": 12, "year": 1}


def ledger_path():
    return cases.home() / "ledger.jsonl"


def _clean_number(value):
    return int(value) if float(value).is_integer() else float(value)


def _records():
    """(records, skipped): every line that fails to decode as UTF-8,
    fails to parse, is not an object or carries a non-numeric or
    over-cap ``saved_per_year`` is skipped and counted. A corrupt or
    oversized line warns, it never sinks the whole ledger."""
    path = ledger_path()
    records, skipped = [], 0
    if path.is_file():
        for raw_line in path.read_bytes().splitlines():
            try:
                line = raw_line.decode("utf-8").strip()
            except UnicodeDecodeError:
                skipped += 1
                continue
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                skipped += 1
                continue
            if not isinstance(record, dict):
                skipped += 1
                continue
            raw = record.get("saved_per_year")
            if raw is not None and cases.num(raw) is None:
                skipped += 1
                continue
            records.append(record)
    return records, skipped


def add(case_dir, before, after, period):
    for v in (before, after):
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or v < 0
            or v > MAX_AMOUNT
        ):
            raise BtError(
                "ledger amounts must be finite non-negative numbers "
                "at most 1e12"
            )
    case_id = Path(case_dir).name
    records, _ = _records()
    if any(r.get("case_id") == case_id for r in records):
        raise BtError("case already recorded in ledger")
    brief = cases.load_brief(case_dir)
    plan = cases.load_plan(case_dir)
    pack = str(brief.get("pack") or case_id.rsplit("-", 2)[0])
    direction = cases.direction_of(brief)
    currency = cases.currency_of(plan, brief)
    multiplier = PERIODS_PER_YEAR[period]
    delta = (after - before) if direction == "receive" else (before - after)
    saved = _clean_number(minor(delta * multiplier))
    if abs(saved) > MAX_AMOUNT:
        # A legal pair can still compound past the cap; it must not
        # land a line the total would only skip.
        raise BtError("ledger savings stay within 1e12 a year")
    record = {
        "case_id": case_id,
        "pack": pack,
        "direction": direction,
        "currency": currency,
        "before": _clean_number(before),
        "after": _clean_number(after),
        "period": period,
        "saved_per_year": saved,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = ledger_path()
    cases.ensure_home()
    # The ledger holds per-case savings; like .floor it is created
    # owner-only. O_NOFOLLOW refuses a symlinked file, O_NONBLOCK
    # makes a fifo fail at open instead of blocking, and fstat proves
    # the fd is a regular file before the append.
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND
        | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise BtError(f"ledger is not a regular file: {path}")
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return saved


def total():
    """Totals grouped by currency: 240 USD a year and 240 EUR a year
    are two answers, never 480. A record without a ``currency`` lands
    in ``unknown`` rather than being guessed into one."""
    records, skipped = _records()
    by_currency = {}
    by_pack = {}
    for r in records:
        saved = cases.num(r.get("saved_per_year")) or 0
        cur = str(r.get("currency") or "unknown")
        by_currency[cur] = by_currency.get(cur, 0) + saved
        pack = str(r.get("pack") or "unknown")
        by_pack.setdefault(pack, {})
        by_pack[pack][cur] = by_pack[pack].get(cur, 0) + saved
    return {
        "cases": len(records),
        "by_currency": {
            c: _clean_number(v) for c, v in sorted(by_currency.items())
        },
        "by_pack": {
            p: {c: _clean_number(v) for c, v in sorted(cs.items())}
            for p, cs in sorted(by_pack.items())
        },
        "warnings": skipped,
    }
