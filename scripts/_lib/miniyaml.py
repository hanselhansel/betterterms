"""YAML loading and dumping helpers.

A thin wrapper over the vendored pure-Python PyYAML in the ``_vendor``
package next to this module (see ``_vendor/README.md``); importing it
through this module keeps ``import yaml`` on sys.path free of it. This
file is byte-copied into other packages, so it must stay free of
repo-rooted paths.

Contract: ``load(text)`` returns what ``yaml.safe_load(text)`` returns,
except that duplicate mapping keys raise :class:`Error` naming the
1-based line and aliases (``*name``) and merge keys (``<<``) raise
:class:`Error`, so anchored data cannot be expanded exponentially or
silently merged. Anchors without aliases are fine. ``dump(obj)`` is
``yaml.dump`` on a SafeDumper that never emits anchors or aliases, with
insertion-order keys, unicode allowed and block (not flow) style.
Documents nested past the interpreter's recursion limit raise
:class:`Error` too. Any failure while parsing or constructing values
surfaces as :class:`Error`, never as ``yaml.YAMLError`` or a bare
``ValueError``/``KeyError``/``TypeError`` from a tag constructor, and
carries the offending node's line when one is known.
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


def _reraise(e, fallback_mark=None):
    mark = getattr(e, "problem_mark", None) or fallback_mark
    raise Error(getattr(e, "problem", None) or str(e), _line(mark)) from e


_MERGE_TAG = "tag:yaml.org,2002:merge"


class _Loader(yaml.SafeLoader):
    """SafeLoader that refuses aliases, merge keys and duplicate
    mapping keys."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            event = self.get_event()
            raise Error(
                f"alias *{event.anchor} is not supported",
                _line(event.start_mark),
            )
        return super().compose_node(parent, index)

    def construct_object(self, node, deep=False):
        # Tag constructors can raise bare exceptions (ValueError from an
        # out-of-range timestamp, KeyError from a bad !!bool value, ...);
        # re-raise them as Error with the node's line so callers get one
        # failure type. Errors already carrying a problem_mark keep it.
        try:
            return super().construct_object(node, deep=deep)
        except (Error, RecursionError):
            raise
        except yaml.YAMLError as e:
            _reraise(e, getattr(node, "start_mark", None))
        except Exception as e:
            detail = str(e) or "failed"
            raise Error(
                f"{type(e).__name__}: {detail}",
                _line(getattr(node, "start_mark", None)),
            ) from e

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                raise Error(
                    "merge key << is not supported",
                    _line(key_node.start_mark),
                )
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
    except RecursionError as e:
        raise Error("nesting too deep") from e
    except yaml.YAMLError as e:
        _reraise(e)
    except Exception as e:
        raise Error(f"{type(e).__name__}: {e or 'failed'}") from e


class _Dumper(yaml.SafeDumper):
    """SafeDumper that never emits anchors or aliases: a shared object
    is written out in full at each site."""

    def ignore_aliases(self, data):
        return True


def dump(obj):
    """Serialize a dict, list or scalar to YAML text."""
    try:
        return yaml.dump(
            obj,
            Dumper=_Dumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    except RecursionError as e:
        raise Error("nesting too deep") from e
    except yaml.YAMLError as e:
        _reraise(e)


__all__ = ["Error", "load", "dump"]
