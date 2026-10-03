"""Case file management under BETTERTERMS_HOME.

Layout: ``$BETTERTERMS_HOME/cases/<case_id>/`` holds ``brief.yaml``,
``plan.yaml``, ``.floor`` (mode 0600, read only by gate and score),
``sources/`` and ``thread.md``. ``BETTERTERMS_HOME`` overrides the
default ``Path.home() / ".betterterms"``. ``case_id`` format:
``<pack>-<YYYYMMDD>-<4 hex>``.
"""

import os
import re
import secrets
from datetime import date
from pathlib import Path

from . import BtError, money, yaml

PACK_RE = re.compile(r"^[a-z0-9-]{1,64}$")
FLOOR_FILE = ".floor"

AUTONOMY_DEFAULT = {"act": 2, "coach": 1}


def home():
    env = os.environ.get("BETTERTERMS_HOME")
    return Path(env).expanduser() if env else Path.home() / ".betterterms"


def case_dir(case_id):
    return home() / "cases" / case_id


def require_case(case_id):
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
    """Parse a single amount from text like ``1200``, ``$1,200.00``,
    ``USD 1200``. Raises BtError unless exactly one number is present.
    The rejected input is never echoed: it may hold the floor."""
    s = text.strip()
    try:
        return float(s.replace(",", ""))
    except ValueError:
        pass
    found = money.amounts(s)
    if len(found) == 1:
        return found[0]
    raise BtError("floor must be a single number")


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
    """Return the floor as float, or None when the file is absent."""
    path = Path(case_dir_path) / FLOOR_FILE
    if not path.is_file():
        return None
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except ValueError:
        raise BtError(f"{path.name}: not a number")
