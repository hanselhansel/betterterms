"""betterterms runtime library. Python stdlib only, no network access."""

MAX_TEXT = 64 * 1024
"""The 64 KB bound on every text the gate or the scorer scans: a
rendered draft, an inbound message, a fact body. Size is checked
before any scanning, so hostile length stays cheap."""


class BtError(Exception):
    """A user-facing runtime error. The CLI prints it as {"error": ...} and
    exits 2."""
