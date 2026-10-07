"""The inbound context an approval binds to.

A held draft (and so an approval marker) names the sha256 of the
canonical inbound message it answered -- a supplied ``--inbound``
mapping, else the case's persisted ``inbound.yaml``, else ``null``
for an opening turn. ``resolve`` returns the mapping the rest of the
turn uses plus that digest; ``digest`` re-derives it for an existing
held record.

The digest binds the complete parsed mapping -- every key and value,
with types preserved -- so two messages that score alike or render
the same reply still hash differently, and an approval can never
answer a message the owner did not review. A numeric ``offer`` and a
string lookalike, and a revision ``1.001`` against ``1.002``, are
distinct values here.

A persisted ``inbound.yaml`` that exists but is unreadable, not a
regular file, oversized or unparseable fails closed (``BtError``):
it is never flattened into the absent-turn digest and never hashed
from a prefix, so two different bad files can never share one
reusable approval context. A genuinely absent file stays an opening
turn.
"""

import hashlib
from pathlib import Path

from . import BtError, inputs

_VERSION = "bt-inbound-context/2"


def _enc(value):
    """Type-tagged canonical encoding of a parsed YAML value: two
    values encode identically only when they are the same type and
    hold the same data, so no coercion ever collapses a changed
    message into a reused approval."""
    if value is None:
        return "n:"
    if isinstance(value, bool):
        return f"b:{int(value)}"
    if isinstance(value, int):
        return f"i:{value}"
    if isinstance(value, float):
        return f"f:{value!r}"
    if isinstance(value, str):
        return f"s{len(value)}:{value}"
    if isinstance(value, list):
        return "l[" + ",".join(_enc(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(
            (_enc(k) + "=" + _enc(v) for k, v in value.items())
        )
        return "m{" + ",".join(items) + "}"
    # A type safe_load can still produce (date, datetime, Decimal):
    # tagged repr keeps distinct values distinct without coercion.
    return f"t:{type(value).__name__}:{value!r}"


def digest(inbound):
    """Hex digest of the canonical inbound mapping, or ``inbound:
    null`` for an opening turn."""
    canon = "inbound:null" if inbound is None else _enc(inbound)
    return hashlib.sha256(
        f"{_VERSION}\n{canon}".encode("utf-8")
    ).hexdigest()


def resolve(case_dir, inbound):
    """Return ``(mapping, digest)`` for the inbound this turn answers:
    a supplied mapping, else the case's persisted ``inbound.yaml``,
    else ``(None, null-digest)`` for an opening turn. A persisted file
    that exists but cannot be fingerprinted whole raises ``BtError``
    rather than collapsing into an opening turn or a shared bad
    digest."""
    if inbound is not None:
        if not isinstance(inbound, dict):
            raise BtError("inbound must be a mapping")
        return inbound, digest(inbound)
    path = Path(case_dir) / "inbound.yaml"
    if not path.is_file():
        if path.exists() or path.is_symlink():
            raise BtError("inbound.yaml is not a readable file")
        return None, digest(None)
    data = inputs.load_yaml_file(path, "inbound.yaml")
    return data, digest(data)
