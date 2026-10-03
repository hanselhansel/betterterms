"""YAML loading and dumping for betterterms dev scripts.

A thin wrapper over the vendored pure-Python PyYAML in
``scripts/_lib/_vendor/yaml`` (see ``_vendor/README.md``); importing it
through this package keeps ``import yaml`` on sys.path free of it.

Contract: ``load(text)`` returns what ``yaml.safe_load(text)`` returns,
except that duplicate mapping keys raise :class:`Error` naming the
1-based line. ``dump(obj)`` is ``yaml.safe_dump`` with insertion-order
keys, unicode allowed and block (not flow) style. YAML failures surface
as :class:`Error`, never as ``yaml.YAMLError``.
"""

from ._vendor import yaml


class Error(Exception):
    """Parse or dump error. ``line`` is 1-based or None."""

    def __init__(self, message, line=None):
        self.line = line
        self.message = message
        super().__init__(f"line {line}: {message}" if line is not None else message)


def _line(mark):
    return mark.line + 1 if mark is not None else None


def _reraise(e):
    mark = getattr(e, "problem_mark", None)
    raise Error(getattr(e, "problem", None) or str(e), _line(mark)) from e


class _Loader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in seen
            except TypeError:
                continue  # unhashable: super() reports it below
            if duplicate:
                raise Error(
                    f"duplicate key {key!r}", _line(key_node.start_mark)
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load(text):
    """Parse a YAML document. Returns dict, list, scalar or None."""
    if not isinstance(text, str):
        raise Error("load() expects a str")
    try:
        return yaml.load(text, Loader=_Loader)
    except Error:
        raise
    except yaml.YAMLError as e:
        _reraise(e)


def dump(obj):
    """Serialize a dict, list or scalar to YAML text."""
    try:
        return yaml.safe_dump(
            obj, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
    except yaml.YAMLError as e:
        _reraise(e)


__all__ = ["Error", "load", "dump"]
