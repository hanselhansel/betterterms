"""Held drafts and hash-bound approvals (spec 6.3, 6.8).

A draft the gate routes to the user lands in ``held/<sha256>.yaml``
beside the case files: the rendered text, the gate's reasons, and when
it was held. An approval for that exact text is
``held/<sha256>.approved``, written only by a user action
(``bt.py held approve``, the mod, or the ``bt approve`` prompt hook).
``bt.py gate --approved`` consumes it: one use, then it is gone and the
held record goes with it. A send of edited text hashes differently, so
a stale approval can never carry over. Files are 0600 under a 0700
``held/`` directory.
"""

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import BtError, yaml

NO_APPROVAL = "no approval recorded for this exact text"

_HASH64 = re.compile(r"[0-9a-f]{64}")
_PREFIX = re.compile(r"[0-9a-f]{8,64}")


def draft_hash(rendered):
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _dir(case_dir):
    return Path(case_dir) / "held"


def _ensure_dir(case_dir):
    d = _dir(case_dir)
    d.mkdir(exist_ok=True)
    os.chmod(d, 0o700)
    return d


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path, text):
    """0600 temp file in the same directory, fsynced and renamed into
    place, like the floor file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".held.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def hold(case_dir, rendered, reasons):
    """Write ``held/<hash>.yaml`` and return the hash. A draft already
    held keeps its first ``held_at``."""
    h = draft_hash(rendered)
    path = _ensure_dir(case_dir) / f"{h}.yaml"
    if not path.exists():
        _write(
            path,
            yaml.dump(
                {
                    "hash": h,
                    "rendered": rendered,
                    "reasons": [str(r) for r in reasons],
                    "held_at": _now(),
                }
            ),
        )
    return h


def list_held(case_dir):
    """Held drafts, oldest first, each with an ``approved`` flag."""
    d = _dir(case_dir)
    out = []
    if d.is_dir():
        for path in d.glob("*.yaml"):
            if not _HASH64.fullmatch(path.stem):
                continue
            data = yaml.load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            data["approved"] = (d / f"{path.stem}.approved").is_file()
            out.append(data)
    out.sort(
        key=lambda e: (str(e.get("held_at") or ""), str(e.get("hash") or ""))
    )
    return out


def resolve(case_dir, hash8):
    """The full hash of the one held draft whose hash starts with
    ``hash8`` (8 to 64 hex). Zero or several matches raise BtError;
    several names every full hash."""
    prefix = str(hash8 or "").strip().lower()
    if not _PREFIX.fullmatch(prefix):
        raise BtError(
            f"expected a draft hash prefix (8+ hex), got {hash8!r}"
        )
    d = _dir(case_dir)
    matches = (
        sorted(
            p.stem
            for p in d.glob("*.yaml")
            if _HASH64.fullmatch(p.stem) and p.stem.startswith(prefix)
        )
        if d.is_dir()
        else []
    )
    if not matches:
        raise BtError(f"no held draft matching {prefix}")
    if len(matches) > 1:
        raise BtError(
            f"{prefix} matches {len(matches)} held drafts: "
            + ", ".join(matches)
        )
    return matches[0]


def approve(case_dir, hash8):
    """Record the user's approval for the held draft: writes
    ``held/<hash>.approved`` and returns the full hash."""
    h = resolve(case_dir, hash8)
    _write(
        _dir(case_dir) / f"{h}.approved",
        yaml.dump({"hash": h, "approved_at": _now()}),
    )
    return h


def reject(case_dir, hash8):
    """Drop the held draft and any approval for it, and record the
    rejection in thread.md. Returns the full hash."""
    h = resolve(case_dir, hash8)
    d = _dir(case_dir)
    for suffix in (".yaml", ".approved"):
        try:
            (d / f"{h}{suffix}").unlink()
        except FileNotFoundError:
            pass
    with (Path(case_dir) / "thread.md").open(
        "a", encoding="utf-8"
    ) as f:
        f.write(f"## rejected {_now()} {h}\n")
    return h


def consume_approval(case_dir, rendered):
    """True once when an approval exists for this exact rendered text:
    the ``.approved`` file and the held record are deleted, so a second
    send of the same text is held again."""
    h = draft_hash(rendered)
    d = _dir(case_dir)
    if not (d / f"{h}.approved").is_file():
        return False
    for suffix in (".approved", ".yaml"):
        try:
            (d / f"{h}{suffix}").unlink()
        except FileNotFoundError:
            pass
    return True
