"""Case file management under BETTERTERMS_HOME.

Layout: ``$BETTERTERMS_HOME/cases/<case_id>/`` holds ``brief.yaml``,
``plan.yaml``, ``.floor`` (mode 0600, read only by gate and score),
``sources/`` and ``thread.md``; the savings ledger lives beside them in
``$BETTERTERMS_HOME/ledger.jsonl``. ``BETTERTERMS_HOME`` overrides the
default ``Path.home() / ".betterterms"``. ``case_id`` format:
``<pack>-<YYYYMMDD>-<4 hex>``.
"""

import math
import os
import re
import secrets
from datetime import date
from pathlib import Path

from . import (
    BtError,
    MAX_AMOUNT,
    PERIODS,
    config,
    inputs,
    worse_than_floor,
    yaml,
)
from .floorio import read_floor, set_floor

PACK_RE = re.compile(r"[a-z0-9-]{1,64}")
CASE_ID_RE = re.compile(r"[a-z0-9-]+")
_CURRENCY = re.compile(r"[A-Za-z]{3}")

AUTONOMY_DEFAULT = {"act": 2, "coach": 1}
OPTION_KINDS = ("bonus", "fee", "price")


def home():
    env = os.environ.get("BETTERTERMS_HOME")
    return Path(env).expanduser() if env else Path.home() / ".betterterms"


def case_dir(case_id):
    return home() / "cases" / case_id


def ensure_home():
    """Create ``BETTERTERMS_HOME`` when missing and pin it to 0700:
    the directory holds case floors and the savings ledger."""
    h = home()
    h.mkdir(parents=True, exist_ok=True)
    os.chmod(h, 0o700)
    return h


def require_case(case_id):
    # Case ids are file names: anything outside [a-z0-9-] could leave
    # the cases directory, so it is rejected before touching the path.
    if not CASE_ID_RE.fullmatch(str(case_id or "")):
        raise BtError(f"bad case id {case_id!r}; expected [a-z0-9-]")
    d = case_dir(case_id)
    if not d.is_dir():
        raise BtError(f"unknown case {case_id!r}")
    return d


def _load(path):
    """Parse a case YAML file through the shared input reader;
    missing file -> {}, missing/empty -> {}. Bad YAML raises BtError."""
    if not path.is_file():
        return {}
    data = inputs.read_yaml_file(path, path.name)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise BtError(f"{path.name}: expected a mapping")
    return data


def load_brief(case_dir_path):
    return _load(Path(case_dir_path) / "brief.yaml")


def load_plan(case_dir_path):
    return _load(Path(case_dir_path) / "plan.yaml")


def new_case_id(pack):
    return f"{pack}-{date.today():%Y%m%d}-{secrets.token_hex(2)}"


def create_case(pack, mode="act", direction="pay"):
    if not PACK_RE.fullmatch(pack):
        raise BtError(f"bad pack name {pack!r}; expected [a-z0-9-]")
    if mode not in AUTONOMY_DEFAULT:
        raise BtError(f"bad mode {mode!r}; expected act or coach")
    if direction not in ("pay", "receive"):
        raise BtError(f"bad direction {direction!r}; expected pay or receive")
    root = ensure_home() / "cases"
    # The config loads before the case folder exists, so a broken
    # config.yaml fails the command without leaving one behind.
    cfg = config.load() if config.path().is_file() else None
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    for _ in range(5):
        case_id = new_case_id(pack)
        d = root / case_id
        try:
            d.mkdir()
        except FileExistsError:
            continue
        os.chmod(d, 0o700)
        (d / "sources").mkdir()
        os.chmod(d / "sources", 0o700)
        brief_data = {
            "pack": pack,
            "mode": mode,
            "direction": direction,
            "goals": [],
            "priorities": [],
            "ranking_check": {"passed": False, "samples": []},
            "autonomy": AUTONOMY_DEFAULT[mode],
            "never_disclose": [],
            "deadline": None,
        }
        plan_data = {
            "target": None,
            "currency": "USD",
            "options": [],
            "ladder": [],
            "patience": {"rounds": None, "days": None},
            "timing": None,
            "channel": None,
            "facts": [],
            "best_alternative": None,
        }
        # An existing config.yaml supplies the new case's autonomy and
        # currency; without one the mode defaults stand (spec 5).
        if cfg is not None:
            brief_data["autonomy"] = cfg["autonomy"]
            plan_data["currency"] = cfg["currency"].upper()
        (d / "brief.yaml").write_text(
            yaml.dump(brief_data),
            encoding="utf-8",
        )
        (d / "plan.yaml").write_text(
            yaml.dump(plan_data),
            encoding="utf-8",
        )
        (d / "thread.md").write_text(
            f"# thread {case_id}\n"
            "# one entry per turn: `## in|out <ISO time> approved_by_user: yes|no`\n",
            encoding="utf-8",
        )
        return case_id, d
    raise BtError("could not allocate a case id")


def as_list(value):
    """Coerce a YAML value to a list. Lists pass through, None -> [], and
    a lone scalar or mapping where a list was expected wraps in one. YAML
    1.1 scalars arrive resolved: ``yes`` is bool True, not the string."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def num(value):
    """Coerce a YAML scalar to float; None and unparseable -> None.
    Magnitudes past the 1e12 cap, infinities and NaN return None too,
    so a hostile number reads as "not a number" and never reaches a
    comparison or an OverflowError."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            v = float(value)
        except OverflowError:
            return None
    elif isinstance(value, str):
        try:
            v = float(value.strip().replace(",", ""))
        except (ValueError, OverflowError):
            return None
    else:
        return None
    return v if math.isfinite(v) and abs(v) <= MAX_AMOUNT else None


def positive(value):
    """``num`` plus the requirement the amount be positive: a zero or
    negative amount is never a price, so it reads as "no usable
    amount" and can never reach a floor comparison."""
    v = num(value)
    return v if v is not None and v > 0 else None


def _plan_value(raw):
    """A plan amount present in the file. ``None`` stays ``None``
    (absent is fine); a numeric value of zero or less is a broken
    plan, never a floor comparison."""
    if raw is None:
        return None
    v = num(raw)
    if v is not None and v <= 0:
        raise BtError("plan conflicts with your limits")
    return v


def direction_of(brief):
    """Brief ``direction``: exactly ``pay`` or ``receive``. Anything else
    is a broken case file, so callers exit 2 instead of defaulting and
    silently applying the wrong inequality."""
    d = str((brief or {}).get("direction") or "").lower()
    if d not in ("pay", "receive"):
        raise BtError("direction must be pay or receive")
    return d


def mode_of(brief):
    """Brief ``mode``: ``act`` or ``coach``, case-insensitive. Anything
    else is a broken case file and exits 2."""
    m = str((brief or {}).get("mode") or "").lower()
    if m not in AUTONOMY_DEFAULT:
        raise BtError("mode must be act or coach")
    return m


def autonomy_of(brief):
    """Brief ``autonomy``: an integer from 1 to 4. Strings like
    ``"1 (draft only)"``, floats and out-of-range values are a broken
    case file and exit 2."""
    a = (brief or {}).get("autonomy")
    if isinstance(a, bool) or not isinstance(a, int) or not 1 <= a <= 4:
        raise BtError("autonomy must be an integer from 1 to 4")
    return a


def period_error(field, value):
    """The broken-period input error, naming the file and key so the
    agent knows exactly what to fix, like ``plan.yaml
    options[1].period``. A null gets the reminder spelled out: only
    inbound.yaml lets an explicit ``period: null`` mean "not
    stated"; everywhere else it is a broken key."""
    msg = f"{field}: must be once, month or year"
    if value is None:
        msg += " (null is not allowed here)"
    return msg


def _period(mapping, key, default, field):
    """``mapping[key]`` as a period. A ``period`` key that is present
    must be a string naming a known period; only an absent key falls
    back to ``default``. A falsy non-string (``null``, ``0``,
    ``false``, ``[]``) is a broken plan, not a default. ``field``
    names the file and key for the error."""
    if not isinstance(mapping, dict) or key not in mapping:
        return default
    value = mapping[key]
    if not isinstance(value, str) or value.lower() not in PERIODS:
        raise BtError(period_error(field, value))
    return value.lower()


def plan_period(plan):
    """The period the plan's values (and the floor) are expressed in."""
    return _period(plan, "period", "once", "plan.yaml period")


def floor_period(plan, brief):
    """The period the floor is expressed in: the plan's explicit
    ``floor_period`` key first, then the plan's ``period``, else the
    brief's, default ``once``. A plan value without its own
    ``period`` is read in this period as well. Every ``period`` key
    present on either file validates even when ``floor_period``
    wins; a broken key cannot hide behind the one that selects."""
    p = _period(
        plan, "floor_period", None, "plan.yaml floor_period"
    )
    periods = [
        _period(doc, "period", "once", f"{name} period")
        for doc, name in ((plan, "plan.yaml"), (brief, "brief.yaml"))
        if isinstance(doc, dict) and "period" in doc
    ]
    return p or (periods[0] if periods else "once")


def currency_of(plan, brief=None):
    """The ISO currency the plan's money is expressed in: the plan's
    ``currency``, else the brief's, default ``USD``. A code that is
    not three letters, or two different declarations, is a broken
    case file: which currency the floor means is unknowable."""
    declared = []
    for doc in (plan, brief):
        if isinstance(doc, dict) and doc.get("currency") is not None:
            c = doc["currency"]
            if not isinstance(c, str) or not _CURRENCY.fullmatch(c):
                raise BtError("currency must be a three-letter ISO code")
            declared.append(c.upper())
    if declared and any(c != declared[0] for c in declared):
        raise BtError("brief and plan declare different currencies")
    return declared[0] if declared else "USD"


def option_kind(item):
    """An option's ``kind``: bonus, fee or price. Only ``price`` options
    are offers checked against the floor."""
    k = str((item or {}).get("kind") or "price").lower()
    if k not in OPTION_KINDS:
        raise BtError(
            f"option {(item or {}).get('label')!r} has unknown kind"
        )
    return k


def check_plan_limits(plan, floor, direction, brief=None):
    """A plan value worse than the floor was built against a different
    limit and must not be negotiated. Only values expressed in the
    floor's declared period conflict: a yearly option next to a
    monthly floor is a different unit, not a violation. Options with
    ``kind`` bonus or fee are not offers and skip the floor
    comparison, but their ``period`` still validates.
    Raises BtError with a message that carries no numbers. Skipped
    when no valid floor exists; that failure is reported by the
    caller's own floor rule."""
    currency_of(plan, brief)
    if floor is None:
        return
    period = floor_period(plan, brief)
    values = [_plan_value(plan.get("target"))]
    for i, item in enumerate(as_list(plan.get("options"))):
        if isinstance(item, dict):
            kind = option_kind(item)
            item_period = _period(
                item, "period", period, f"plan.yaml options[{i}].period"
            )
            v = _plan_value(item.get("value"))
            if kind == "price" and item_period == period:
                values.append(v)
    for i, item in enumerate(as_list(plan.get("ladder"))):
        if isinstance(item, dict):
            item_period = _period(
                item, "period", period, f"plan.yaml ladder[{i}].period"
            )
            v = _plan_value(item.get("value"))
            if item_period == period:
                values.append(v)
    # A fact's period defaults to ``once``; anything else invalid is a
    # broken plan. The ``amount`` field itself never joins ``values``:
    # a fact states what the counterparty said, not a price on offer.
    # But a malformed amount must fail closed here, not parse to null
    # downstream where render and the floor rules would read it as
    # "no structured amount".
    for i, item in enumerate(as_list(plan.get("facts"))):
        if isinstance(item, dict):
            _period(
                item, "period", "once", f"plan.yaml facts[{i}].period"
            )
            amount = item.get("amount")
            n = num(amount)
            if amount is not None and (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or n is None
            ):
                raise BtError("fact amount must be a number or null")
            if n is not None and n <= 0:
                raise BtError(
                    "fact amount must be a positive number or null"
                )
    # ``best_alternative`` (spec 6.4) is context for the agent, never an
    # offer: its shape validates here, but its amount never joins
    # ``values`` for the floor comparison.
    alt = plan.get("best_alternative")
    if alt is not None:
        if not isinstance(alt, dict):
            raise BtError("best_alternative must be a mapping")
        _period(
            alt,
            "period",
            "once",
            "best alternative period must be once, month or year",
        )
        amount = alt.get("amount")
        if amount is not None and (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or num(amount) is None
            or num(amount) <= 0
        ):
            raise BtError(
                "best_alternative amount must be a positive number or null"
            )
    for v in values:
        if v is not None and worse_than_floor(v, floor, direction):
            raise BtError("plan conflicts with your limits")
