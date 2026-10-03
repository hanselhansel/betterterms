"""Savings ledger. One JSON line per closed case in
``$BETTERTERMS_HOME/ledger.jsonl``. ``saved_per_year`` is positive when
the outcome is better than before: ``before - after`` for ``pay`` cases,
``after - before`` for ``receive`` cases, times the periods per year.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from . import BtError, MAX_AMOUNT, cases

PERIODS_PER_YEAR = {"month": 12, "year": 1}


def ledger_path():
    return cases.home() / "ledger.jsonl"


def _clean_number(value):
    return int(value) if float(value).is_integer() else float(value)


def _records():
    """(records, skipped): every line that fails to parse, is not an
    object or carries a non-numeric or over-cap ``saved_per_year`` is
    skipped and counted. A corrupt or oversized line warns, it never
    sinks the whole ledger."""
    path = ledger_path()
    records, skipped = [], 0
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
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
    pack = str(brief.get("pack") or case_id.rsplit("-", 2)[0])
    direction = cases.direction_of(brief)
    multiplier = PERIODS_PER_YEAR[period]
    delta = (after - before) if direction == "receive" else (before - after)
    saved = _clean_number(delta * multiplier)
    if abs(saved) > MAX_AMOUNT:
        # A legal pair can still compound past the cap; it must not
        # land a line the total would only skip.
        raise BtError("ledger savings stay within 1e12 a year")
    record = {
        "case_id": case_id,
        "pack": pack,
        "direction": direction,
        "before": _clean_number(before),
        "after": _clean_number(after),
        "period": period,
        "saved_per_year": saved,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return saved


def total():
    records, skipped = _records()
    by_pack = {}
    saved_total = 0
    for r in records:
        saved = cases.num(r.get("saved_per_year")) or 0
        saved_total += saved
        pack = str(r.get("pack") or "unknown")
        by_pack[pack] = by_pack.get(pack, 0) + saved
    return {
        "cases": len(records),
        "saved_per_year": _clean_number(saved_total),
        "by_pack": {p: _clean_number(v) for p, v in sorted(by_pack.items())},
        "warnings": skipped,
    }
