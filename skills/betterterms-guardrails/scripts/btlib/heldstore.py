"""Storage primitives for held drafts and approval markers.

A held draft lives at ``held/<sha256>.yaml`` where the sha256
covers the send tuple: action, normalized offer, period, case
currency, the exact rendered text and the reviewed inbound's
context digest (``btlib.context``). An approval marker lives beside
it at ``held/<sha256>.approved``. This module owns the record
shape, the canonical hash, integrity checks and atomic file IO;
``btlib.held`` owns the lifecycle verbs that call them.

The hash covers the tuple's canonical form -- the offer in
two-decimal money, the rest verbatim -- so two different tuples can
never share a filename, and a record whose stored fields do not
hash back to its name (strict field presence and types, checked by
``record_ok``) is corrupt or tampered and can never authorize a
send. Files are 0600 under a 0700 ``held/`` directory.
"""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import cases, minor, yaml

HASH64 = re.compile(r"[0-9a-f]{64}")
# Pre-context records hashed only these five fields; ``legacy_ok``
# still recognizes them so an old held draft explains itself.
TUPLE_KEYS_V1 = ("action", "offer", "period", "currency", "rendered")
TUPLE_KEYS = TUPLE_KEYS_V1 + ("inbound",)


def make_record(action, offer, period, currency, rendered,
                inbound=None):
    """The held record's send tuple: one canonical field set the
    hash, the widgets and the tests all share."""
    return {
        "action": action,
        "offer": offer,
        "period": period,
        "currency": currency,
        "rendered": rendered,
        "inbound": inbound,
    }


def draft_record(case_dir, draft, rendered, context=None):
    """The send tuple for a gate call on ``draft``: the fields
    normalized the way ``gate.check`` reads them, the exact rendered
    text and the inbound context digest."""
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
    # A caller that supplies no context still binds the record -- to
    # the opening-turn digest, never to a null that any real inbound
    # tuple could collide with.
    if context is None:
        from . import context as _ctxmod

        context = _ctxmod.digest(None)
    return make_record(
        action,
        offer,
        period,
        cases.currency_of(
            cases.load_plan(case_dir), cases.load_brief(case_dir)
        ),
        rendered,
        context,
    )


def _tuple_hash(record, keys):
    """SHA-256 of the canonical send tuple over ``keys``. The offer is
    written in its two-decimal money form so 1100 and 1100.0 hash
    alike; a missing offer is null, never zero."""
    offer = cases.num(record.get("offer"))
    canon = json.dumps(
        {
            **{k: record.get(k) for k in keys},
            "offer": None if offer is None else f"{minor(offer):.2f}",
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def draft_hash(record):
    return _tuple_hash(record, TUPLE_KEYS)


def record_ok(data, stem):
    """A record is trustworthy only when its stored tuple -- every
    field present with its written type, so a re-typed offer or a
    dropped inbound field fails -- hashes back to its filename."""
    if not isinstance(data, dict) or data.get("hash") != stem:
        return False
    if not HASH64.fullmatch(stem):
        return False
    if not all(k in data for k in TUPLE_KEYS):
        return False
    if not (
        isinstance(data["action"], str)
        and isinstance(data["period"], str)
        and isinstance(data["currency"], str)
        and isinstance(data["rendered"], str)
        and isinstance(data["inbound"], str)
        and HASH64.fullmatch(data["inbound"])
        and isinstance(data.get("reasons"), list)
        and isinstance(data.get("held_at"), str)
    ):
        return False
    offer = data["offer"]
    if offer is not None and (
        isinstance(offer, bool)
        or not isinstance(offer, (int, float))
        # cases.num normalizes to the stored form: a NaN, an
        # infinity, a magnitude past the cap or a re-typed string
        # collapses to None or a different value, and a nonpositive
        # amount was never writable by the gate (offer <= 0 blocks),
        # so all of these mark the record as tampered.
        or cases.num(offer) != offer
        or offer <= 0
    ):
        return False
    return draft_hash({k: data[k] for k in TUPLE_KEYS}) == stem


def legacy_ok(data, stem):
    """A record from before the current hash shape: the rendered text
    alone, or the five-field pre-context tuple. Either may list
    flagged ``legacy`` and be rejected, but can never be approved or
    spent: the answer is to re-run the gate."""
    if not isinstance(data, dict) or data.get("hash") != stem:
        return False
    if not HASH64.fullmatch(stem):
        return False
    rendered = data.get("rendered")
    if not isinstance(rendered, str):
        return False
    if hashlib.sha256(rendered.encode("utf-8")).hexdigest() == stem:
        return True
    return _tuple_hash(data, TUPLE_KEYS_V1) == stem


def held_dir(case_dir):
    return Path(case_dir) / "held"


def ensure_dir(case_dir):
    d = held_dir(case_dir)
    d.mkdir(exist_ok=True)
    os.chmod(d, 0o700)
    return d


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unlink(*paths):
    for p in paths:
        try:
            p.unlink()
        except OSError:
            pass


def read_yaml(path):
    """Parsed YAML mapping or list, or None on any read/parse
    failure -- a corrupt file reads as absent rather than raising
    into a caller that treats absence safely."""
    try:
        return yaml.load(path.read_text(encoding="utf-8"))
    except (yaml.Error, UnicodeDecodeError, OSError):
        return None


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
