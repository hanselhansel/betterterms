"""betterterms runtime library. Python stdlib only, no network access."""


class BtError(Exception):
    """A user-facing runtime error. The CLI prints it as {"error": ...} and
    exits 2."""
