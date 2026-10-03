"""betterterms runtime library. Python stdlib only, no network access."""

MAX_TEXT = 64 * 1024
"""The 64 KB bound on every text the gate or the scorer scans: a
rendered draft, an inbound message, a fact body. Size is checked
before any scanning, so hostile length stays cheap."""

MAX_AMOUNT = 1e12
"""Largest magnitude the toolkit treats as a number: offers, plan
values, ledger amounts and money-scan results past it parse to
nothing, never to an uncapped float."""

FLOOR_TOL = 0.005
"""Absolute tolerance for "equal to the floor" comparisons, so a
floor entered as 1200.00 still matches a rendered 1200."""

PERIODS = ("once", "month", "year")
"""The only billing periods a draft, option or inbound offer may
declare. ``once`` is the default and converts against nothing."""


class BtError(Exception):
    """A user-facing runtime error. The CLI prints it as {"error": ...} and
    exits 2."""
