"""Research source records under ``cases/<id>/sources/<n>.yaml``.

A source record is one finding: ``url``, ``read_at`` (ISO date),
``quote`` (verbatim text), ``trust`` (``official``, ``regulator``,
``press`` or ``forum``) and ``used_for``, plus optional ``amount``
(number or null) and ``period`` (``once``, ``month`` or ``year``) when
the finding states money, which the plan copies into a fact's
``amount`` and ``period``. ``add`` validates a record
piped on stdin and writes the next numbered file; ``list_records``
reads them back in order; ``stale`` flags records older than a day
count, plus any record whose date cannot be read at all: an undated
claim cannot be shown fresh, so it is flagged for re-check.
"""

import math
import os
import re
from datetime import date, datetime
from pathlib import Path

from . import BtError, MAX_AMOUNT, PERIODS, yaml

FIELDS = ("url", "read_at", "quote", "trust", "used_for")
OPTIONAL_FIELDS = ("amount", "period")
TRUST_LEVELS = ("official", "regulator", "press", "forum")
FILE_RE = re.compile(r"^(\d+)\.yaml$")


def _number(path):
    m = FILE_RE.match(path.name)
    return int(m.group(1)) if m else None


def _sources_dir(case_dir):
    return Path(case_dir) / "sources"


def parse_date(value):
    """An ISO date as a ``datetime.date``. Accepts a date or datetime
    object (YAML resolves unquoted timestamps) or a string the ISO
    parsers accept; a datetime string keeps its date part."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            pass
    raise BtError("read_at must be an ISO date like 2026-10-03")


def validate_record(data):
    """Validate a source record mapping. Returns a clean record with
    ``read_at`` as a date and ``trust`` lowercased. All five fields are
    required; unknown fields and empty strings fail closed. ``amount``
    and ``period`` are optional and validated like a plan fact's."""
    if not isinstance(data, dict):
        raise BtError("source record must be a mapping")
    known = FIELDS + OPTIONAL_FIELDS
    unknown = sorted(str(k) for k in data if k not in known)
    if unknown:
        raise BtError(f"source record: unknown fields {', '.join(unknown)}")
    for field in ("url", "quote", "used_for"):
        v = data.get(field)
        if not isinstance(v, str) or not v.strip():
            raise BtError(f"source record: {field} must be a non-empty string")
    trust = str(data.get("trust") or "").strip().lower()
    if trust not in TRUST_LEVELS:
        raise BtError(f"trust must be one of {', '.join(TRUST_LEVELS)}")
    record = {
        "url": data["url"].strip(),
        "read_at": parse_date(data.get("read_at")),
        "quote": data["quote"].strip(),
        "trust": trust,
        "used_for": data["used_for"].strip(),
    }
    # Optional money fields mirror a plan fact's `amount`/`period`
    # (decision 0010): a real number or null, a period from PERIODS.
    if "amount" in data:
        amount = data["amount"]
        if amount is not None and (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or abs(amount) > MAX_AMOUNT
        ):
            raise BtError("source record: amount must be a number or null")
        record["amount"] = amount
    if "period" in data:
        period = str(data["period"] or "once").lower()
        if period not in PERIODS:
            raise BtError("source record: period must be once, month or year")
        record["period"] = period
    elif "amount" in record and record["amount"] is not None:
        record["period"] = "once"
    return record


def add(case_dir, data):
    """Validate ``data`` and write ``sources/<n>.yaml`` with the next
    free number (max existing + 1, so an id is never reused and a plan
    fact's ``source`` cannot silently point at a different finding).
    The number is reserved by an exclusive create, so two adds that
    read the same next number never overwrite each other: the loser
    retries on the following id. Returns ``(source_id, path)``."""
    record = validate_record(data)
    d = _sources_dir(case_dir)
    d.mkdir(parents=True, exist_ok=True)
    n = max((_number(p) for p in d.iterdir() if _number(p)), default=0) + 1
    text = yaml.dump(record)
    for _ in range(100):
        path = d / f"{n}.yaml"
        try:
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            n += 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return str(n), path
    raise BtError("could not reserve a source id")


def _load(path):
    try:
        data = yaml.load(path.read_text(encoding="utf-8"))
    except yaml.Error as e:
        raise BtError(f"{path.name}: {e}")
    if not isinstance(data, dict):
        raise BtError(f"{path.name}: expected a mapping")
    return data


def list_records(case_dir):
    """All source records sorted by number, each with its ``id``.
    Only ``<n>.yaml`` files are records; anything else in the directory
    is ignored. A malformed record file raises BtError naming it."""
    d = _sources_dir(case_dir)
    files = [p for p in d.iterdir() if _number(p)] if d.is_dir() else []
    records = []
    for p in sorted(files, key=_number):
        rec = _load(p)
        rec["id"] = str(_number(p))
        records.append(rec)
    return records


def stale(case_dir, days):
    """Records whose ``read_at`` is strictly more than ``days`` old.
    A record with a missing or unreadable date is flagged too, with
    ``age_days`` None."""
    if days < 0:
        raise BtError("days must be a non-negative integer")
    today = date.today()
    out = []
    for rec in list_records(case_dir):
        try:
            age = (today - parse_date(rec.get("read_at"))).days
        except BtError:
            rec["age_days"] = None
            out.append(rec)
            continue
        if age > days:
            rec["age_days"] = age
            out.append(rec)
    return out
