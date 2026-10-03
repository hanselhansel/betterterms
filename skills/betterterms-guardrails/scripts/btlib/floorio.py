"""The ``.floor`` file: one plain number per case, written atomically
and read back defensively.

``set_floor`` never touches a symlinked or non-regular target and
lands the new value through a 0600 temp file in the same directory,
fsynced and renamed into place, so a concurrent reader can never see
a torn floor. ``read_floor`` lstat-checks the path and treats
anything but a regular file as missing: a bad floor is a limit
failure, never a guess.
"""

import math
import os
import re
import stat
import tempfile
from pathlib import Path

from . import BtError

FLOOR_FILE = ".floor"
FLOOR_MSG = "floor must be a single plain number like 1200 or 1200.50"
FLOOR_MIN = "floor must be at least 0.01"
_PLAIN_NUMBER = re.compile(r"\d+(?:\.\d{1,2})?")
_REFUSE = "refusing to write the floor file"


def parse_number(text):
    """Parse a floor value: one plain number like ``1200`` or
    ``1200.50``. Currency marks, separators, signs, exponents, spelled
    forms and extra decimals are all ambiguous, so they are rejected
    with one fixed message that never echoes the input: the input may
    hold the floor. The stored form is money, so a third decimal or a
    value below a cent cannot be carried exactly and is rejected too."""
    m = _PLAIN_NUMBER.fullmatch(str(text or "").strip())
    value = None
    if m:
        try:
            value = float(m.group(0))
        except ValueError:
            value = None
    if value is None or not math.isfinite(value):
        raise BtError(FLOOR_MSG)
    if value < 0.01:
        raise BtError(FLOOR_MIN)
    return value


def set_floor(case_dir_path, raw):
    """Write the floor file (mode 0600) in its canonical two-decimal
    form. The value is never echoed. The target is opened with
    ``O_NOFOLLOW`` and must be a regular file: a planted symlink can
    never point the write outside the case. The new value lands
    through a same-directory temp file, fsynced and renamed with
    ``os.replace``."""
    value = parse_number(raw)
    path = Path(case_dir_path) / FLOOR_FILE
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        fd = None
    except OSError as e:
        raise BtError(_REFUSE) from e
    if fd is not None:
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise BtError(_REFUSE)
        finally:
            os.close(fd)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".floor.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{value:.2f}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_floor(case_dir_path):
    """Floor as float, or None when the file is missing, is a symlink
    or any non-regular file, is unreadable or undecodable, or holds
    anything ``parse_number`` rejects. Callers must fail closed."""
    path = Path(case_dir_path) / FLOOR_FILE
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        return parse_number(raw)
    except BtError:
        return None
