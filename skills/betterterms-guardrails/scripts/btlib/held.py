"""Held drafts and hash-bound approvals (spec 6.3, 6.8).

A draft the gate routes to the user lands in ``held/<sha256>.yaml``
beside the case files. The hash binds the whole send: the draft's
action, offer, period and the case currency plus the exact rendered
text, JSON-encoded in sorted-key order. An approval for that tuple is
``held/<hash>.approved``, written only by a user action
(``bt.py held approve``, the mod, or the ``bt approve`` prompt hook).
``bt.py gate --approved`` consumes it atomically: the marker unlinks
once, then the held record goes with it, so two racing sends cannot
share one approval. The same words under a different action or offer
hash differently, so an approval can never carry to a stronger verb.
An approval sticks only to the draft the last recorded gate verdict
held: ``gate.json`` names that hash, and ``held approve`` refuses
any other one, a held record written by hand, or a case whose
verdict was pass or block or never ran.
A held record whose stored fields do not hash back to its filename is
corrupt or tampered with and stays invisible to ``held list`` and the
widgets. Files are 0600 under a 0700 ``held/`` directory.
"""

import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import BtError, cases, minor, yaml

NO_APPROVAL = "no approval recorded for this exact text"
LEGACY = "held by an older version; re-run the gate"

_HASH64 = re.compile(r"[0-9a-f]{64}")
_PREFIX = re.compile(r"[0-9a-f]{8,64}")

# The fields an approval binds; draft_hash serializes them in this
# fixed order under json sort_keys.
_TUPLE_KEYS = ("action", "offer", "period", "currency", "rendered")


def make_record(action, offer, period, currency, rendered):
    """One send tuple as a plain dict."""
    return {
        "action": action,
        "offer": offer,
        "period": period,
        "currency": currency,
        "rendered": rendered,
    }


def draft_record(case_dir, draft, rendered):
    """The send tuple for a gate call on ``draft``: the fields
    normalized the way ``gate.check`` reads them (numeric offer or
    None, lowercase period defaulting to ``once``, the case currency)
    and the exact rendered text."""
    case_dir = Path(case_dir)
    if isinstance(draft, dict):
        action = draft.get("action")
        action = action if isinstance(action, str) else None
        raw_period = draft.get("period")
        period = (
            "once"
            if raw_period is None
            else str(raw_period).lower()
        )
        offer = cases.num(draft.get("offer"))
    else:
        action, period, offer = None, "once", None
    return make_record(
        action,
        offer,
        period,
        cases.currency_of(
            cases.load_plan(case_dir), cases.load_brief(case_dir)
        ),
        rendered,
    )


def draft_hash(record):
    """SHA-256 of the canonical send tuple. The offer is written in its
    two-decimal money form so 1100 and 1100.0 hash alike; a missing
    offer is null, never zero."""
    offer = cases.num(record.get("offer"))
    canon = json.dumps(
        {
            **{k: record.get(k) for k in _TUPLE_KEYS},
            "offer": None if offer is None else f"{minor(offer):.2f}",
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _record_ok(data, stem):
    """A held record is trustworthy only when the tuple it stored
    hashes back to its own filename; anything else is corrupt or
    tampered and never reaches a listing, a widget or an approval."""
    if not isinstance(data, dict) or data.get("hash") != stem:
        return False
    if not _HASH64.fullmatch(stem):
        return False
    return draft_hash({k: data.get(k) for k in _TUPLE_KEYS}) == stem


def _legacy_ok(data, stem):
    """A record from before approvals bound the send tuple: its name
    is the SHA-256 of the rendered text alone. It may list (flagged
    ``legacy`` so the mod skips it) and it may be rejected, but it can
    never be approved or spent: the answer is to re-run the gate."""
    if not isinstance(data, dict) or data.get("hash") != stem:
        return False
    if not _HASH64.fullmatch(stem):
        return False
    rendered = data.get("rendered")
    if not isinstance(rendered, str):
        return False
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest() == stem


def _dir(case_dir):
    return Path(case_dir) / "held"


def _ensure_dir(case_dir):
    d = _dir(case_dir)
    d.mkdir(exist_ok=True)
    os.chmod(d, 0o700)
    return d


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path, text):
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


def hold(case_dir, draft, rendered, reasons):
    """Write ``held/<hash>.yaml`` for this send tuple and return the
    hash. A draft already held keeps its first ``held_at``."""
    record = draft_record(case_dir, draft, rendered)
    h = draft_hash(record)
    path = _ensure_dir(case_dir) / f"{h}.yaml"
    if not path.exists():
        atomic_write(
            path,
            yaml.dump(
                {
                    "hash": h,
                    **{k: record[k] for k in _TUPLE_KEYS},
                    "reasons": [str(r) for r in reasons],
                    "held_at": _now(),
                }
            ),
        )
    return h


def list_held(case_dir):
    """Held drafts, oldest first, each with an ``approved`` flag. A
    record whose stored fields do not hash to its name is skipped;
    one whose name is the old text-only hash lists flagged
    ``legacy`` with a re-run-the-gate note, since an approval for it
    can never match a current tuple."""
    d = _dir(case_dir)
    out = []
    if d.is_dir():
        for path in d.glob("*.yaml"):
            if not _HASH64.fullmatch(path.stem):
                continue
            data = yaml.load(path.read_text(encoding="utf-8"))
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


def _current_hash(case_dir):
    """The hash the last recorded gate verdict held, or None. The
    gate writes ``gate.json`` on every verdict but sets ``hash`` only
    on needs_approval, so a missing or malformed file, a verdict of
    any other kind, and a hash of the wrong type all read as no
    current draft."""
    try:
        data = json.loads(
            (Path(case_dir) / "gate.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    h = data.get("hash")
    return h if isinstance(h, str) else None


def approve(case_dir, hash8):
    """Record the user's approval for the held draft: writes
    ``held/<hash>.approved`` and returns the full hash. A record whose
    stored fields no longer hash to its name is corrupt and cannot be
    approved; one from before tuple-bound hashes gets the re-run
    answer instead. The hash must also be the one the last gate
    verdict held: a stale card, a hand-written record, and a case
    with no recorded verdict all refuse."""
    h = resolve(case_dir, hash8)
    d = _dir(case_dir)
    data = yaml.load((d / f"{h}.yaml").read_text(encoding="utf-8"))
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


def drop(case_dir, hash8):
    """Drop the held draft and any approval marker, like reject but
    with no thread.md entry: the record's content was edited or
    superseded, not refused, so no marker is owed. Returns the full
    hash."""
    h = resolve(case_dir, hash8)
    d = _dir(case_dir)
    for suffix in (".yaml", ".approved"):
        try:
            (d / f"{h}{suffix}").unlink()
        except FileNotFoundError:
            pass
    return h


def supersede(case_dir, new_hash):
    """Drop the record the last gate verdict held when ``new_hash``
    replaces it: one draft is current at a time. Quiet like
    ``drop`` -- the old text was superseded, not refused, so no
    thread marker. The gate calls this right after ``hold``; the
    ``gate.json`` it reads still names the previous verdict's hash,
    and a same-hash or missing record is left alone. Returns the
    dropped hash or None."""
    prev = _current_hash(case_dir)
    if prev is None or prev == new_hash:
        return None
    try:
        return drop(case_dir, prev)
    except BtError:
        return None


def consume_approval(case_dir, draft, rendered):
    """True once when an approval exists for this exact send tuple:
    the ``.approved`` marker is claimed by renaming it to a unique
    name, an atomic take on POSIX -- a plain unlink can report success
    to two racing callers on filesystems that resolve the deletion
    lazily -- so two racing sends can never share one approval. The
    held record goes with the claimed marker."""
    record = draft_record(case_dir, draft, rendered)
    h = draft_hash(record)
    d = _dir(case_dir)
    claim = d / f".{h}.{os.getpid()}.{secrets.token_hex(4)}.claimed"
    try:
        os.rename(d / f"{h}.approved", claim)
    except OSError:
        return False
    for path in (claim, d / f"{h}.yaml"):
        try:
            path.unlink()
        except OSError:
            pass
    return True
