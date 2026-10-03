"""Case file management under BETTERTERMS_HOME.

Layout: ``$BETTERTERMS_HOME/cases/<case_id>/`` holds ``brief.yaml``,
``plan.yaml``, ``.floor`` (mode 0600, read only by gate and score),
``sources/`` and ``thread.md``. ``BETTERTERMS_HOME`` overrides the
default ``Path.home() / ".betterterms"``. ``case_id`` format:
``<pack>-<YYYYMMDD>-<4 hex>``.
"""

import math
import os
import re
import secrets
from datetime import date
from pathlib import Path

from . import BtError, yaml

PACK_RE = re.compile(r"^[a-z0-9-]{1,64}$")
CASE_ID_RE = re.compile(r"^[a-z0-9-]+$")
FLOOR_FILE = ".floor"
FLOOR_MSG = "floor must be a single plain number like 1200 or 1200.50"
_PLAIN_NUMBER = re.compile(r"\d+(?:\.(\d+))?$")

AUTONOMY_DEFAULT = {"act": 2, "coach": 1}
PERIODS = ("once", "month", "year")
OPTION_KINDS = ("bonus", "fee", "price")


def home():
    env = os.environ.get("BETTERTERMS_HOME")
    return Path(env).expanduser() if env else Path.home() / ".betterterms"


def case_dir(case_id):
    return home() / "cases" / case_id


def require_case(case_id):
    # Case ids are file names: anything outside [a-z0-9-] could leave
    # the cases directory, so it is rejected before touching the path.
    if not CASE_ID_RE.match(str(case_id or "")):
        raise BtError(f"bad case id {case_id!r}; expected [a-z0-9-]")
    d = case_dir(case_id)
    if not d.is_dir():
        raise BtError(f"unknown case {case_id!r}")
    return d


def _load(path):
    """Parse a YAML file; missing file -> {}, missing/empty -> {}.
    Bad YAML raises BtError."""
    if not path.is_file():
        return {}
    try:
        data = yaml.load(path.read_text(encoding="utf-8"))
    except yaml.Error as e:
        raise BtError(f"{path.name}: {e}")
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
    if not PACK_RE.match(pack):
        raise BtError(f"bad pack name {pack!r}; expected [a-z0-9-]")
    if mode not in AUTONOMY_DEFAULT:
        raise BtError(f"bad mode {mode!r}; expected act or coach")
    if direction not in ("pay", "receive"):
        raise BtError(f"bad direction {direction!r}; expected pay or receive")
    root = home() / "cases"
    root.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        case_id = new_case_id(pack)
        d = root / case_id
        try:
            d.mkdir()
        except FileExistsError:
            continue
        (d / "sources").mkdir()
        (d / "brief.yaml").write_text(
            yaml.dump(
                {
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
            ),
            encoding="utf-8",
        )
        (d / "plan.yaml").write_text(
            yaml.dump(
                {
                    "target": None,
                    "currency": "USD",
                    "options": [],
                    "ladder": [],
                    "patience": {"rounds": None, "days": None},
                    "timing": None,
                    "channel": None,
                    "facts": [],
                }
            ),
            encoding="utf-8",
        )
        (d / "thread.md").write_text(
            f"# thread {case_id}\n"
            "# one entry per turn: `## in|out <ISO time> approved_by_user: yes|no`\n",
            encoding="utf-8",
        )
        return case_id, d
    raise BtError("could not allocate a case id")


def parse_number(text):
    """Parse a floor value: one plain number like ``1200`` or
    ``1200.50``. Currency marks, separators, signs, exponents, spelled
    forms and extra decimals are all ambiguous, so they are rejected
    with one fixed message that never echoes the input: the input may
    hold the floor. A three-digit decimal tail (``85.000``) is a
    thousands separator in some locales, so it is rejected too."""
    m = _PLAIN_NUMBER.fullmatch(str(text or "").strip())
    value = None
    if m and (m.group(1) is None or len(m.group(1)) != 3):
        try:
            value = float(m.group(0))
        except ValueError:
            value = None
    if value is None or not math.isfinite(value):
        raise BtError(FLOOR_MSG)
    return value


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
    """Coerce a YAML scalar to float; None and unparseable -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", ""))
        except ValueError:
            return None
    return None


def num_repr(value):
    f = float(value)
    return str(int(f)) if f.is_integer() else repr(f)


def set_floor(case_dir_path, raw):
    """Write the floor file (mode 0600). The value is never echoed."""
    value = parse_number(raw)
    path = Path(case_dir_path) / FLOOR_FILE
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(num_repr(value) + "\n")
    os.chmod(path, 0o600)


def read_floor(case_dir_path):
    """Floor as float, or None when the file is missing, unreadable or
    holds anything ``parse_number`` rejects. A bad floor is a limit
    failure, never a guess: callers must fail closed."""
    path = Path(case_dir_path) / FLOOR_FILE
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return parse_number(raw)
    except BtError:
        return None


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


def plan_period(plan):
    """The period the plan's values (and the floor) are expressed in."""
    p = str((plan or {}).get("period") or "once").lower()
    if p not in PERIODS:
        raise BtError("plan period must be once, month or year")
    return p


def floor_period(plan, brief):
    """The period the floor is expressed in: the plan's ``period``,
    else the brief's, default ``once``. A plan value without its own
    ``period`` is read in this period as well."""
    for doc in (plan, brief):
        if isinstance(doc, dict) and doc.get("period") is not None:
            return plan_period(doc)
    return "once"


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
    ``kind`` bonus or fee are not offers and skip the check entirely.
    Raises BtError with a message that carries no numbers. Skipped
    when no valid floor exists; that failure is reported by the
    caller's own floor rule."""
    if floor is None:
        return
    period = floor_period(plan, brief)
    values = [num(plan.get("target"))]
    for item in as_list(plan.get("options")):
        if isinstance(item, dict) and option_kind(item) == "price":
            item_period = str(item.get("period") or period).lower()
            if item_period not in PERIODS:
                raise BtError("option period must be once, month or year")
            if item_period == period:
                values.append(num(item.get("value")))
    for item in as_list(plan.get("ladder")):
        if isinstance(item, dict):
            item_period = str(item.get("period") or period).lower()
            if item_period not in PERIODS:
                raise BtError("ladder period must be once, month or year")
            if item_period == period:
                values.append(num(item.get("value")))
    for v in values:
        if v is None:
            continue
        if not math.isfinite(v) or (
            direction == "receive" and v < floor
        ) or (
            direction == "pay" and v > floor
        ):
            raise BtError("plan conflicts with your limits")
