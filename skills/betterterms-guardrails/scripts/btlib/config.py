"""The user config file at ``<BETTERTERMS_HOME>/config.yaml`` (spec 5).

Intake reads it to prefill new cases; drafting skills read ``sign_off``
and ``voice_notes`` straight from it. The gate and the approval path
never read it. The file is mode 0600, written atomically like the
floor file.
"""

import os
import re
import sys
import tempfile

from . import BtError, yaml

DEFAULTS = {
    "autonomy": 2,
    "currency": "USD",
    "sign_off": "",
    "voice_notes": "",
}

_CURRENCY = re.compile(r"[A-Za-z]{3}")


def path():
    from . import cases
    return cases.home() / "config.yaml"


def _check(key, value):
    """One config value; a bad value raises BtError naming the key."""
    if key == "autonomy":
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= 4
        ):
            raise BtError("autonomy must be an integer from 1 to 4")
    elif key == "currency":
        if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
            raise BtError("currency must be a three-letter ISO code")
    elif not isinstance(value, str):
        raise BtError(f"{key} must be a string")


def _warn(msg):
    print(f"bt: config.yaml: {msg}", file=sys.stderr)


def load():
    """The merged config: DEFAULTS under whatever the file sets.

    A missing file returns the defaults. An unknown key warns on
    stderr and is ignored; a bad value raises BtError naming the key.
    """
    p = path()
    if not p.is_file():
        return dict(DEFAULTS)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise BtError(f"config.yaml: {e}") from e
    try:
        data = yaml.load(text)
    except yaml.Error as e:
        raise BtError(f"config.yaml: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise BtError("config.yaml: expected a mapping")
    cfg = dict(DEFAULTS)
    for key, value in data.items():
        if key not in DEFAULTS:
            _warn(f"ignoring unknown key {key!r}")
            continue
        _check(key, value)
        cfg[key] = value
    return cfg


def set_value(key, raw):
    """Set one config key from a CLI string, write the file 0600, and
    return the merged config."""
    if key not in DEFAULTS:
        raise BtError(
            f"unknown config key {key!r}; expected one of "
            + ", ".join(sorted(DEFAULTS))
        )
    value = raw
    if key == "autonomy":
        try:
            value = int(str(raw).strip())
        except ValueError:
            raise BtError("autonomy must be an integer from 1 to 4")
    elif key == "currency":
        value = str(raw).strip().upper()
    _check(key, value)
    cfg = load()
    cfg[key] = value
    _write(cfg)
    return cfg


def _write(cfg):
    """Atomic 0600 write of the full merged config, like the floor."""
    from . import cases
    root = cases.ensure_home()
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".config.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(yaml.dump({k: cfg[k] for k in DEFAULTS}))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
