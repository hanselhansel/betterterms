"""The one reader for YAML input files.

Every YAML file the runtime consumes -- the case ``brief.yaml`` and
``plan.yaml``, a gate ``--draft`` or ``--inbound``, or a ``sources/``
record when a command reads one -- goes through this module, so the
input bounds live in exactly one place.

Two refusals raise :class:`UnsafeInput`:

- a file over ``MAX_TEXT`` bytes, refused before it is read into
  memory;
- a document nested deeper than 32 levels, refused by the loader
  during parsing (``btlib/yaml.py``) so a hostile file stays cheap
  instead of walking the parser into the interpreter's recursion
  limit.

``UnsafeInput`` is a ``BtError``: callers that do not handle it get
the plain exit-2 error path (the brief and plan readers), while the
gate and the scorer catch it for draft and inbound and report a
fail-closed block at exit 1. Everything else -- a missing file, bad
YAML, an undecodable file, a non-mapping document -- stays ``BtError``
exactly as before.
"""

from pathlib import Path

from . import BtError, MAX_TEXT, yaml


class UnsafeInput(BtError):
    """A YAML input refused on size or depth."""


def read_yaml_file(path, what):
    """Read and parse one YAML input file under the input bounds.
    Returns the parsed document, whatever its shape; callers decide
    which shapes they accept."""
    p = Path(path)
    if not p.is_file():
        raise BtError(f"{what} file not found: {path}")
    try:
        if p.stat().st_size > MAX_TEXT:
            raise UnsafeInput(f"{what}: file too large (over 64 KB)")
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise BtError(f"{what}: {e}") from e
    try:
        return yaml.load(text)
    except yaml.Error as e:
        # The depth refusal (and the recursion-limit fallback, which
        # reports the same message) is an UnsafeInput for draft and
        # inbound; every other parse failure stays a plain error.
        if "nesting too deep" in e.message:
            raise UnsafeInput(f"{what}: {e}") from e
        raise BtError(f"{what}: {e}") from e


def load_yaml_file(path, what):
    """``read_yaml_file`` plus the mapping shape every input document
    takes."""
    data = read_yaml_file(path, what)
    if not isinstance(data, dict):
        raise BtError(f"{what}: expected a mapping")
    return data
