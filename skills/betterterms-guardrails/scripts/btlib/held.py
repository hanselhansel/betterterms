"""Held drafts and the approval markers that release them.

A draft that lands in the review tier (``gate.check`` -> ``hold``)
is written to ``held/<sha256>.yaml`` (``btlib.heldstore`` owns the
record shape, hash and file IO). Approving writes
``held/<sha256>.approved``, only through a user action
(``bt.py held approve``, the mod, or the ``bt approve`` prompt
hook). ``bt.py gate --approved`` consumes the marker atomically:
the marker is claimed by rename first, then validated, then the
held record goes with it, so two racing sends cannot share one
approval and a swap between read and rename can never authorize a
corrupt marker. The same words under a different action, offer or
inbound context hash differently, so an approval can never carry
to a stronger verb or a message the owner did not review.

An approval sticks only to the draft the last recorded gate verdict
held (``gate.json`` names that hash), and consent survives only
while its valid record continuously exists: ``supersede`` scans
``held/`` itself -- never ``gate.json``, which a later verdict
rewrites -- and retires every other record and every non-current
marker, valid file or orphan alike, so a stale marker can never
resurrect onto a later same-hash record. ``consume_approval``
refuses a marker whose record is missing, corrupt or no longer the
current ``needs_approval`` verdict's hash.
"""

import json
import os
import re
import secrets
from pathlib import Path

from . import BtError, heldstore, yaml
from .heldstore import (
    atomic_write, draft_hash, draft_record, held_dir, make_record,
)

LEGACY = "held by an older version; re-run the gate"
NO_APPROVAL = "no approval recorded for this exact text"
_PREFIX = re.compile(r"[0-9a-f]{8,64}")
_record_ok = heldstore.record_ok
_legacy_ok = heldstore.legacy_ok
_read = heldstore.read_yaml
_unlink = heldstore.unlink
_HASH64 = heldstore.HASH64
_TUPLE_KEYS = heldstore.TUPLE_KEYS


def hold(case_dir, draft, rendered, reasons, context=None):
    """Write ``held/<hash>.yaml`` for this send tuple and return the
    hash. An identical record already held keeps its ``held_at`` and
    any unspent approval; a marker left behind by a removed or
    corrupted record is stale and retires before the write, so it
    can never attach to a fresh same-hash record."""
    record = draft_record(case_dir, draft, rendered, context)
    h = draft_hash(record)
    d = heldstore.ensure_dir(case_dir)
    path = d / f"{h}.yaml"
    if _record_ok(_read(path), h):
        return h
    _unlink(d / f"{h}.approved")
    atomic_write(
        path,
        yaml.dump(
            {
                "hash": h,
                **{k: record[k] for k in _TUPLE_KEYS},
                "reasons": [str(r) for r in reasons],
                "held_at": heldstore.now(),
            }
        ),
    )
    return h


def list_held(case_dir):
    """Held drafts, oldest first, each with an ``approved`` flag.
    Unreadable or tampered records are skipped; a record whose name
    is an older hash shape lists flagged ``legacy`` with a
    re-run-the-gate note, since an approval can never match it."""
    d = held_dir(case_dir)
    out = []
    if d.is_dir():
        for path in d.glob("*.yaml"):
            if not _HASH64.fullmatch(path.stem):
                continue
            data = _read(path)
            if _record_ok(data, path.stem):
                pass
            elif _legacy_ok(data, path.stem):
                data["legacy"] = True
                data["note"] = LEGACY
            else:
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
    d = held_dir(case_dir)
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


def _current_hash(case_dir):
    """The hash the last recorded gate verdict held, or None. Only a
    well-formed ``needs_approval`` verdict counts: a pass or block
    verdict, a malformed file, and a hash of the wrong shape all
    read as no current draft, so stale consent can never spend."""
    try:
        data = json.loads(
            (Path(case_dir) / "gate.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    h = data.get("hash")
    if (
        data.get("result") != "needs_approval"
        or not isinstance(h, str)
        or not _HASH64.fullmatch(h)
    ):
        return None
    return h


def approve(case_dir, hash8):
    """Record the user's approval for the held draft: writes
    ``held/<hash>.approved`` and returns the full hash. A corrupt or
    legacy record refuses, and the hash must be the one the last
    recorded ``needs_approval`` verdict held."""
    h = resolve(case_dir, hash8)
    d = held_dir(case_dir)
    data = _read(d / f"{h}.yaml")
    if not _record_ok(data, h):
        if _legacy_ok(data, h):
            raise BtError(f"held draft {h[:8]} is {LEGACY}")
        raise BtError(f"held draft {h[:8]} is corrupt")
    if _current_hash(case_dir) != h:
        raise BtError(
            f"held draft {h[:8]} is not the current held draft; "
            "approve the hash the last gate call printed"
        )
    atomic_write(
        d / f"{h}.approved",
        yaml.dump({"hash": h, "approved_at": heldstore.now()}),
    )
    return h


def reject(case_dir, hash8):
    """Drop the held draft and any approval for it, and record the
    rejection in thread.md. Returns the full hash."""
    h = resolve(case_dir, hash8)
    d = held_dir(case_dir)
    _unlink(d / f"{h}.yaml", d / f"{h}.approved")
    with (Path(case_dir) / "thread.md").open(
        "a", encoding="utf-8"
    ) as f:
        f.write(f"## rejected {heldstore.now()} {h}\n")
    return h


def drop(case_dir, hash8):
    """Drop the held draft and any approval marker, like reject but
    with no thread.md entry. Returns the full hash."""
    h = resolve(case_dir, hash8)
    d = held_dir(case_dir)
    _unlink(d / f"{h}.yaml", d / f"{h}.approved")
    return h


def supersede(case_dir, new_hash):
    """Retire every held record and approval marker that is not
    ``new_hash``: one draft is current at a time, so the gate calls
    this on every verdict (``new_hash`` None retires all). The scan
    reads ``held/`` itself, never ``gate.json``. A marker goes
    whenever its hash is not current -- even when its record is
    missing or corrupt -- so an orphan can never resurrect onto a
    later same-hash record. A legacy record keeps its file for the
    re-run note but its marker still retires. Quiet like ``drop``."""
    d = held_dir(case_dir)
    if not d.is_dir():
        return None
    dropped = None
    for path in sorted(d.glob("*.yaml")):
        stem = path.stem
        if stem == new_hash or not _HASH64.fullmatch(stem):
            continue
        data = _read(path)
        if _record_ok(data, stem):
            _unlink(path)
            dropped = stem
    for marker in d.glob("*.approved"):
        if marker.stem != new_hash:
            _unlink(marker)
    return dropped


def consume_approval(case_dir, draft, rendered, context=None):
    """True once when an approval exists for this exact send tuple.
    The ``.approved`` marker is claimed by renaming it to a unique
    name first -- an atomic take on POSIX, and the claimed file is
    what gets validated, so a swap between read and rename can never
    authorize a corrupt marker -- then the held record goes with it.
    A marker spends only when its record hashes back to its name,
    the claimed marker names that hash, and the record is still the
    current verdict's hash. A marker whose record is missing or
    corrupt is retired unreadable, never spendable."""
    record = draft_record(case_dir, draft, rendered, context)
    h = draft_hash(record)
    d = held_dir(case_dir)
    rec_path, marker = d / f"{h}.yaml", d / f"{h}.approved"
    if not marker.is_file():
        return False
    if not rec_path.is_file():
        _unlink(marker)
        return False
    claim = d / f".{h}.{os.getpid()}.{secrets.token_hex(4)}.claimed"
    try:
        os.rename(marker, claim)
    except OSError:
        return False
    mark, data = _read(claim), _read(rec_path)
    if not (
        _record_ok(data, h)
        and isinstance(mark, dict)
        and mark.get("hash") == h
        and _current_hash(case_dir) == h
    ):
        _unlink(claim)
        if not _record_ok(data, h):
            _unlink(rec_path)
        return False
    _unlink(claim, rec_path)
    return True
