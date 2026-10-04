"""Savings ledger. One JSON line per closed case in
``$BETTERTERMS_HOME/ledger.jsonl``. ``saved_per_year`` is positive when
the outcome is better than before: ``before - after`` for ``pay`` cases,
``after - before`` for ``receive`` cases, times the periods per year,
rounded to the currency minor unit. A ``once`` deal records the delta
as ``saved_once`` instead: a one-time saving is never a rate, so it
stays out of the per-year totals entirely.
"""

import fcntl
import json
import math
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from . import BtError, MAX_AMOUNT, cases, minor

PERIODS_PER_YEAR = {"once": 1, "month": 12, "year": 1}


def ledger_path():
    return cases.home() / "ledger.jsonl"


def _clean_number(value):
    return int(value) if float(value).is_integer() else float(value)


def _parse_records(data):
    """(records, skipped) from ledger bytes: every line that fails to
    decode as UTF-8, fails to parse (a line nested past the
    interpreter limit raises RecursionError, which counts the same),
    is not an object or carries a non-numeric or over-cap
    ``saved_per_year`` is skipped and counted. A corrupt or oversized
    line warns, it never sinks the whole ledger."""
    records, skipped = [], 0
    for raw_line in data.splitlines():
        try:
            line = raw_line.decode("utf-8").strip()
        except UnicodeDecodeError:
            skipped += 1
            continue
        if not line:
            continue
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            skipped += 1
            continue
        if not isinstance(record, dict):
            skipped += 1
            continue
        bad = False
        for key in ("saved_per_year", "saved_once"):
            raw = record.get(key)
            if raw is not None and cases.num(raw) is None:
                bad = True
                break
        if bad:
            skipped += 1
            continue
        records.append(record)
    return records, skipped


def _read_locked(exclusive):
    """(fd, data): the ledger under an flock. A shared lock for
    readers, which get ``(None, bytes)``; an exclusive one for the
    read-dedupe-append sequence in ``add``, which gets the open fd
    and the locked snapshot to dedupe against, so two processes can
    never record the same case twice. A missing ledger reads as
    empty; a non-regular file (symlink, fifo) fails closed."""
    path = ledger_path()
    if exclusive:
        cases.ensure_home()
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    else:
        flags = os.O_RDONLY
    try:
        fd = os.open(
            path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
        )
    except FileNotFoundError:
        return None, b""
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BtError(f"ledger is not a regular file: {path}")
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        data = os.pread(fd, os.fstat(fd).st_size, 0)
    except BaseException:
        os.close(fd)
        raise
    if exclusive:
        return fd, data
    os.close(fd)
    return None, data


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
        # A one-time deal is a delta taken once: it lands under
        # ``saved_once`` and never inflates the per-year figures.
        "saved_once" if period == "once" else "saved_per_year": saved,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # The ledger holds per-case savings; like .floor it is created
    # owner-only. O_NOFOLLOW refuses a symlinked file, O_NONBLOCK
    # makes a fifo fail at open instead of blocking, and fstat proves
    # the fd is a regular file before the append. The dedupe read and
    # the append run under one exclusive flock, so a racing add of
    # the same case loses instead of double-recording.
    fd, data = _read_locked(exclusive=True)
    try:
        records, _ = _parse_records(data)
        if any(r.get("case_id") == case_id for r in records):
            raise BtError("case already recorded in ledger")
        line = json.dumps(record, sort_keys=True) + "\n"
        # A file that ends mid-line still gets a clean append: the
        # record lands on a line of its own.
        out = line if data.endswith(b"\n") or not data else "\n" + line
        os.write(fd, out.encode("utf-8"))
    finally:
        os.close(fd)
    return saved


def total():
    """Totals grouped by currency: 240 USD a year and 240 EUR a year
    are two answers, never 480. One-time savings stay in their own
    ``once_by_*`` maps rather than masquerading as a yearly rate. A
    record without a ``currency`` lands in ``unknown`` rather than
    being guessed into one."""
    records, skipped = _parse_records(_read_locked(exclusive=False)[1])
    by_currency = {}
    by_pack = {}
    once_by_currency = {}
    once_by_pack = {}

    def bump(table, cur, pack_table, pack, value):
        table[cur] = table.get(cur, 0) + value
        pack_table.setdefault(pack, {})
        pack_table[pack][cur] = pack_table[pack].get(cur, 0) + value

    for r in records:
        cur = str(r.get("currency") or "unknown")
        pack = str(r.get("pack") or "unknown")
        saved = cases.num(r.get("saved_per_year"))
        if saved is not None:
            bump(by_currency, cur, by_pack, pack, saved)
        once = cases.num(r.get("saved_once"))
        if once is not None:
            bump(once_by_currency, cur, once_by_pack, pack, once)
    return {
        "cases": len(records),
        "by_currency": {
            c: _clean_number(v) for c, v in sorted(by_currency.items())
        },
        "once_by_currency": {
            c: _clean_number(v) for c, v in sorted(once_by_currency.items())
        },
        "by_pack": {
            p: {c: _clean_number(v) for c, v in sorted(cs.items())}
            for p, cs in sorted(by_pack.items())
        },
        "once_by_pack": {
            p: {c: _clean_number(v) for c, v in sorted(cs.items())}
            for p, cs in sorted(once_by_pack.items())
        },
        "warnings": skipped,
    }
