"""Character-level helpers for :mod:`miniyaml`. Import miniyaml, not this.

Holds the shared Error type, scalar resolution (int, float, bool, null,
plain string), quoted-string and flow ``[a, b]`` / ``{k: v}`` parsers, the
``key: rest`` splitter, the comment stripper, and the dump-side scalar
renderers.
"""

import json
import math
import re

_INT_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(r"^[+-]?([0-9]+\.[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$|^[+-]?[0-9]+[eE][+-]?[0-9]+$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class Error(Exception):
    """Parse or dump error. The message includes the line number."""

    def __init__(self, message, line=None):
        self.line = line
        super().__init__(f"line {line}: {message}" if line is not None else message)


# --- loading: scalar and flow parsing -----------------------------------------

def _plain(s):
    low = s.lower()
    if low in ("", "null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    return s


def _scalar(s, ln):
    s = s.strip()
    if not s:
        return None
    if s[0] in "\"'[{":
        val, pos = _quoted_or_flow(s, 0, ln)
        if s[pos:].strip():
            raise Error("trailing characters after scalar", ln)
        return val
    if s[0] in "&*!%@`":
        raise Error(f"unsupported indicator {s[0]!r} (anchors, aliases and tags are not supported)", ln)
    return _plain(s)


def _key(s, ln):
    """Resolve a mapping key. Quoted keys unquote; plain keys resolve like
    plain scalars so ``1: x`` maps under int 1 and round-trips."""
    if s[0] in "\"'":
        return _quoted(s, 0, ln)[0]
    return _plain(s)


def _quoted_or_flow(s, pos, ln):
    if s[pos] in "[{":
        return _flow(s, pos, ln)
    return _quoted(s, pos, ln)


_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "0": "\0", "a": "\a", "b": "\b",
    "f": "\f", "v": "\v", "e": "\x1b", '"': '"', "'": "'", "\\": "\\",
    "/": "/", " ": " ", "_": " ",
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
                elif e in "xu":
                    n = 2 if e == "x" else 4
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
            key, pos = _flow_scalar(s, pos, ln, key=True)
            pos = _skip_ws(s, pos)
            if pos >= len(s) or s[pos] != ":":
                raise Error("expected ':' in flow mapping", ln)
            value, pos = _flow_value(s, pos + 1, ln)
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


def _flow_value(s, pos, ln):
    pos = _skip_ws(s, pos)
    if pos >= len(s):
        raise Error("unexpected end of flow collection", ln)
    if s[pos] in "[{":
        return _flow(s, pos, ln)
    return _flow_scalar(s, pos, ln)


def _flow_scalar(s, pos, ln, key=False):
    pos = _skip_ws(s, pos)
    if pos < len(s) and s[pos] in "\"'":
        return _quoted(s, pos, ln)
    start = pos
    while pos < len(s):
        c = s[pos]
        if c in ",]}" or (key and c == ":"):
            break
        if not key and c == ":" and (pos + 1 >= len(s) or s[pos + 1] in " ,]}"):
            break
        pos += 1
    return _plain(s[start:pos].strip()), pos


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
        return repr(v)
    if isinstance(v, dict):
        return "{}"
    if isinstance(v, list):
        return "[]"
    if isinstance(v, str):
        return v if _plain_safe(v) else json.dumps(v, ensure_ascii=False)
    raise Error(f"cannot dump value of type {type(v).__name__}")


_AMBIGUOUS_PLAIN = {"yes", "no", "on", "off", "y", "n"}


def _plain_safe(s):
    """A string may dump unquoted when it cannot parse back as anything
    else and carries no indicator characters, comments or edges. YAML 1.1
    booleans (yes/no/on/off/y/n), dates, and hex/octal-looking values must
    also be quoted so stricter parsers read them back as strings."""
    if not s or s != s.strip():
        return False
    if s[0] in "-?:,[]{}#&*!|>'\"%@`":
        return False
    if any(c in s for c in "[]{}\"';"):
        return False
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in s):
        return False
    if ": " in s or s.endswith(":") or " #" in s:
        return False
    low = s.lower()
    if low in _AMBIGUOUS_PLAIN or low.startswith(("0x", "0o")):
        return False
    if _DATE_RE.match(s):
        return False
    if _plain(s) is not s:
        return False
    return True
