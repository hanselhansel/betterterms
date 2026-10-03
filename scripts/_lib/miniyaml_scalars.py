"""Character-level helpers for :mod:`miniyaml`. Import miniyaml, not this.

Holds the shared Error type, scalar resolution (int, float, bool, null,
plain string), quoted-string and flow ``[a, b]`` / ``{k: v}`` parsers, the
``key: rest`` splitter, the comment stripper, and the dump-side scalar
renderers.
"""

import json
import math
import re

# Scalars this subset resolves. Anything else a full YAML parser would
# resolve to a non-string type raises instead of returning a wrong value.
_INT_RE = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)$")
_FLOAT_RE = re.compile(
    r"^[+-]?[0-9]+\.[0-9]*(?:[eE][-+][0-9]+)?$|^\.[0-9]+(?:[eE][-+][0-9]+)?$"
)
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

# PyYAML implicit resolvers outside the subset. Matching scalars raise so
# load never returns a value yaml.safe_load would resolve differently.
_YAML_BOOL_RE = re.compile(
    r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|"
    r"on|On|ON|off|Off|OFF)$"
)
_YAML_INT_RE = re.compile(
    r"^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)"
    r"|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$"
)
_YAML_FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?"
    r"|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?"
    r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)
_YAML_TS_RE = re.compile(
    r"^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
    r"|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?"
    r"(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?"
    r"(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$"
)

_NULLS = {"", "~", "null", "Null", "NULL"}
_TRUE = {"true", "True", "TRUE"}
_FALSE = {"false", "False", "FALSE"}
_TAG_SCALARS = {"=", "<<"}


class Error(Exception):
    """Parse or dump error. The message includes the line number."""

    def __init__(self, message, line=None):
        self.line = line
        self.message = message
        super().__init__(f"line {line}: {message}" if line is not None else message)


# --- loading: scalar and flow parsing -----------------------------------------

def _plain(s, ln):
    """Resolve a plain scalar. Strings a full YAML parser would resolve to
    a non-string type raise instead of returning a different value."""
    if s in _NULLS:
        return None
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    if s in _TAG_SCALARS:
        raise Error(f"{s!r} resolves as a YAML tag; quote it", ln)
    if (
        _YAML_BOOL_RE.match(s)
        or _YAML_INT_RE.match(s)
        or _YAML_FLOAT_RE.match(s)
        or _YAML_TS_RE.match(s)
    ):
        raise Error(f"plain scalar {s!r} resolves to a non-string in full YAML; quote it", ln)
    return s


def _scalar(s, ln):
    if "\t" in s:
        raise Error("tabs are not allowed in scalars", ln)
    s = s.strip()
    if not s:
        return None
    if s[0] in "\"'[{":
        val, pos = _quoted_or_flow(s, 0, ln)
        if s[pos:].strip():
            raise Error("trailing characters after scalar", ln)
        return val
    if s[0] in "&*!%@`":
        raise Error(
            f"unsupported indicator {s[0]!r} "
            "(anchors, aliases and tags are not supported)",
            ln,
        )
    if s[0] in "|>":
        raise Error("block scalar indicator must follow 'key:' on the same line", ln)
    if s[0] in ",]}" or (s[0] in "-?:" and (len(s) == 1 or s[1] == " ")):
        raise Error(f"scalar {s!r} starts with an indicator character", ln)
    if ": " in s or s.endswith(":"):
        raise Error(f"plain scalar {s!r} needs quoting", ln)
    return _plain(s, ln)


def _key(s, ln):
    """Resolve a mapping key. Quoted keys unquote; plain keys resolve like
    plain scalars so ``1: x`` maps under int 1 and round-trips."""
    if s == "?" or s.startswith("? "):
        raise Error("explicit '?' keys are not supported", ln)
    if s[0] in "\"'":
        return _quoted(s, 0, ln)[0]
    return _plain(s, ln)


def _quoted_or_flow(s, pos, ln):
    if s[pos] in "[{":
        return _flow(s, pos, ln)
    return _quoted(s, pos, ln)


_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "0": "\0", "a": "\a", "b": "\b",
    "f": "\f", "v": "\v", "e": "\x1b", '"': '"', "'": "'", "\\": "\\",
    "/": "/", " ": " ", "_": "\xa0", "N": "\x85", "L": "\u2028",
    "P": "\u2029",
}


def _quoted(s, pos, ln):
    """Parse a quoted scalar at s[pos]. Returns (value, pos_after)."""
    if s[pos] == '"':
        pos += 1
        out = []
        while pos < len(s):
            c = s[pos]
            if c == '"':
                return "".join(out), pos + 1
            if c == "\\":
                pos += 1
                if pos >= len(s):
                    raise Error("unterminated escape", ln)
                e = s[pos]
                if e in _ESCAPES:
                    out.append(_ESCAPES[e])
                elif e in "xuU":
                    n = {"x": 2, "u": 4, "U": 8}[e]
                    digits = s[pos + 1:pos + 1 + n]
                    if len(digits) != n or not _HEX_RE.match(digits):
                        raise Error("bad escape", ln)
                    out.append(chr(int(digits, 16)))
                    pos += n
                else:
                    raise Error(f"unknown escape \\{e}", ln)
            else:
                out.append(c)
            pos += 1
        raise Error("unterminated string", ln)
    pos += 1
    out = []
    while pos < len(s):
        c = s[pos]
        if c == "'":
            if pos + 1 < len(s) and s[pos + 1] == "'":
                out.append("'")
                pos += 1
            else:
                return "".join(out), pos + 1
        else:
            out.append(c)
        pos += 1
    raise Error("unterminated string", ln)


def _skip_ws(s, pos):
    while pos < len(s) and s[pos] == " ":
        pos += 1
    return pos


def _flow(s, pos, ln):
    """Parse a flow ``[...]`` or ``{...}`` collection. Returns (value, pos)."""
    pos = _skip_ws(s, pos)
    if pos >= len(s):
        raise Error("expected flow collection", ln)
    opener = s[pos]
    closer = "]" if opener == "[" else "}"
    out = [] if opener == "[" else {}
    pos = _skip_ws(s, pos + 1)
    if pos < len(s) and s[pos] == closer:
        return out, pos + 1
    while pos < len(s):
        if opener == "{":
            key, pos = _flow_scalar(s, pos, ln)
            pos = _skip_ws(s, pos)
            if pos >= len(s) or s[pos] != ":":
                raise Error("expected ':' in flow mapping", ln)
            value, pos = _flow_value(s, pos + 1, ln, allow_empty=True)
            try:
                out[key] = value
            except TypeError:
                raise Error("unhashable flow mapping key", ln)
        else:
            value, pos = _flow_value(s, pos, ln)
            out.append(value)
        pos = _skip_ws(s, pos)
        if pos >= len(s):
            raise Error(f"unterminated flow collection, expected '{closer}'", ln)
        if s[pos] == ",":
            pos = _skip_ws(s, pos + 1)
            if pos < len(s) and s[pos] == closer:
                return out, pos + 1
            continue
        if s[pos] == closer:
            return out, pos + 1
        raise Error(f"expected ',' or '{closer}'", ln)
    raise Error(f"unterminated flow collection, expected '{closer}'", ln)


def _flow_value(s, pos, ln, allow_empty=False):
    pos = _skip_ws(s, pos)
    if pos >= len(s):
        raise Error("unexpected end of flow collection", ln)
    if s[pos] in "[{":
        return _flow(s, pos, ln)
    return _flow_scalar(s, pos, ln, allow_empty=allow_empty)


def _flow_scalar(s, pos, ln, allow_empty=False):
    pos = _skip_ws(s, pos)
    if pos < len(s) and s[pos] in "\"'":
        return _quoted(s, pos, ln)
    start = pos
    while pos < len(s):
        c = s[pos]
        if c in ",]}":
            break
        if c == ":" and (pos + 1 >= len(s) or s[pos + 1] in " ,]}"):
            break
        pos += 1
    text = s[start:pos].strip()
    if not text:
        if not allow_empty:
            raise Error("empty entry in flow collection", ln)
        return None, pos
    if text == "?" or text.startswith("? "):
        raise Error("explicit '?' keys are not supported", ln)
    return _plain(text, ln), pos


def _split_key(text):
    """Split ``key: rest`` at the first colon outside quotes and flow
    collections that ends the line or precedes a space. Returns
    (key_text, rest) or None."""
    in_s = in_d = False
    depth = 0
    prev = None
    i = 0
    while i < len(text):
        c = text[i]
        if in_d:
            if c == "\\":
                i += 1
            elif c == '"':
                in_d = False
        elif in_s:
            if c == "'":
                in_s = False
        elif c in "\"'" and (prev is None or prev in ":-[{,"):
            if c == '"':
                in_d = True
            else:
                in_s = True
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == ":" and depth == 0 and (i + 1 == len(text) or text[i + 1] == " "):
            key_text = text[:i].strip()
            if not key_text:
                return None
            return key_text, text[i + 1:]
        if c != " ":
            prev = c
        i += 1
    return None


def _strip_comment(content):
    """Cut a ``#`` comment. ``#`` starts a comment only at line start or
    after a space, and never inside a quoted scalar."""
    in_s = in_d = False
    prev = None
    i = 0
    while i < len(content):
        c = content[i]
        if in_d:
            if c == "\\":
                i += 1
            elif c == '"':
                in_d = False
        elif in_s:
            if c == "'":
                in_s = False
        elif c in "\"'" and (prev is None or prev in ":-[{,"):
            if c == '"':
                in_d = True
            else:
                in_s = True
        elif c == "#" and (i == 0 or content[i - 1] == " "):
            return content[:i]
        if c != " ":
            prev = c
        i += 1
    return content


# --- dumping -----------------------------------------------------------------

def _key_repr(k):
    if k is None or isinstance(k, (str, int, float, bool)):
        return _scalar_repr(k)
    raise Error(f"cannot dump key of type {type(k).__name__}")


def _scalar_repr(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise Error(f"cannot dump non-finite float {v!r}")
        r = repr(v)
        if "." not in r and "e" in r:
            r = r.replace("e", ".0e", 1)
        return r
    if isinstance(v, dict):
        return "{}"
    if isinstance(v, list):
        return "[]"
    if isinstance(v, str):
        if _plain_safe(v):
            return v
        # Escape line-break chars PyYAML would treat as real breaks even
        # inside quotes; other non-ASCII stays readable.
        esc = any(c in v for c in "\x85\u2028\u2029")
        return json.dumps(v, ensure_ascii=esc)
    raise Error(f"cannot dump value of type {type(v).__name__}")


# Plain strings PyYAML keeps as strings but other YAML 1.1 readers resolve
# to a non-string. Dumping them quoted keeps the value stable everywhere.
_EXTRA_QUOTE_RE = re.compile(
    r"^(?:[yYnN]|[-+]?0[oO][0-7_]+"
    r"|[-+]?(?:[0-9][0-9_]*(?:\.[0-9_]*)?|\.[0-9][0-9_]*)[eE][-+]?[0-9]+)$"
)


def _plain_safe(s):
    """A string may dump unquoted when it cannot parse back as anything
    else and carries no indicator characters, comments or edges."""
    if not s or s != s.strip():
        return False
    if s[0] in "-?:,[]{}#&*!|>'\"%@`":
        return False
    if any(c in s for c in "[]{}\"';"):
        return False
    if s[0] == "\ufeff" or any(c in s for c in "\x85\u2028\u2029"):
        return False
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in s):
        return False
    if ": " in s or s.endswith(":") or " #" in s:
        return False
    if _EXTRA_QUOTE_RE.match(s):
        return False
    try:
        return _plain(s, None) is s
    except Error:
        return False
