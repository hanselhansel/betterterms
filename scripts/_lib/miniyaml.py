"""A small YAML subset reader/writer, stdlib only.

Supported: block mappings, block sequences, flow ``[a, b]`` and ``{k: v}``,
single and double quoted scalars, plain scalars resolving to int, float,
bool or null, ``#`` comments, and ``|`` / ``>`` block scalars. A sequence
may sit at the same indent as its parent key. Anything else raises
:class:`Error` naming the 1-based line number.

Plain ``yes``/``no``/``on``/``off`` stay strings; only ``true``/``false``
are booleans. ``load`` parses a single document and ignores one leading
``---`` marker.
"""

from .miniyaml_scalars import (
    Error,
    _key,
    _key_repr,
    _scalar,
    _scalar_repr,
    _split_key,
    _strip_comment,
)

BLOCK_STYLES = ("|", ">", "|-", "|+", ">-", ">+")


# --- loading -----------------------------------------------------------------

def load(text):
    """Parse a YAML subset document. Returns dict, list, scalar or None."""
    if not isinstance(text, str):
        raise Error("load() expects a str")
    raw = [line.removesuffix("\r") for line in text.split("\n")]
    return _Parser(raw).parse()


def _tokenize(raw):
    """Return [(lineno, indent, content)] with blank and comment-only lines
    dropped and trailing comments stripped. Tabs in indentation raise."""
    tokens = []
    for n, line in enumerate(raw, 1):
        indent = 0
        for ch in line:
            if ch == " ":
                indent += 1
            elif ch == "\t":
                raise Error("tab indentation is not allowed", n)
            else:
                break
        content = _strip_comment(line[indent:]).rstrip()
        if content:
            tokens.append((n, indent, content))
    return tokens


class _Parser:
    def __init__(self, raw):
        self.raw = raw
        self.tok = _tokenize(raw)
        self.i = 0

    def parse(self):
        while self.i < len(self.tok) and self.tok[self.i][2] == "---" and self.tok[self.i][1] == 0:
            self.i += 1
        if self.i >= len(self.tok):
            return None
        value = self.block(self.tok[self.i][1])
        if self.i < len(self.tok):
            raise Error("unexpected content", self.tok[self.i][0])
        return value

    def block(self, indent):
        """Parse the node starting at the current token, which must sit at
        ``indent``. Returns the value and consumes its tokens."""
        ln, ind, text = self.tok[self.i]
        if ind > indent:
            raise Error("unexpected indentation", ln)
        if text == "-" or text.startswith("- "):
            return self.seq(indent)
        if _split_key(text) is not None:
            return self.map(indent)
        self.i += 1
        if self.i < len(self.tok) and self.tok[self.i][1] > ind:
            raise Error("unexpected indentation", self.tok[self.i][0])
        return _scalar(text, ln)

    def map(self, indent, first=None):
        out = {}
        pending = first
        while True:
            if pending is not None:
                ln, (key_text, rest) = pending
                pending = None
            else:
                if self.i >= len(self.tok):
                    break
                ln, ind, text = self.tok[self.i]
                if ind != indent or text == "-" or text.startswith("- "):
                    break
                kv = _split_key(text)
                if kv is None:
                    raise Error("expected 'key: value'", ln)
                self.i += 1
                key_text, rest = kv
            key = _key(key_text, ln)
            if key in out:
                raise Error(f"duplicate key {key!r}", ln)
            out[key] = self.value_after_key(rest, ln, indent)
        return out

    def value_after_key(self, rest, ln, indent):
        """Value for a ``key:`` entry. ``rest`` is the text after the colon;
        when empty the value is a nested block, a same-indent sequence, or
        null. The entry line is already consumed."""
        rest = rest.strip()
        if rest in BLOCK_STYLES:
            value, last_ln = self.block_scalar(ln, indent, rest)
            while self.i < len(self.tok) and self.tok[self.i][0] <= last_ln:
                self.i += 1
            return value
        if rest:
            return _scalar(rest, ln)
        if self.i < len(self.tok):
            nind, ntext = self.tok[self.i][1], self.tok[self.i][2]
            if nind > indent:
                return self.block(nind)
            if nind == indent and (ntext == "-" or ntext.startswith("- ")):
                return self.seq(indent)
        return None

    def seq(self, indent, first=None):
        items = []
        pending = first
        while True:
            if pending is not None:
                ln, ind, text = pending
                pending = None
            else:
                if self.i >= len(self.tok):
                    break
                ln, ind, text = self.tok[self.i]
                if ind != indent or not (text == "-" or text.startswith("- ")):
                    break
                self.i += 1
            rest = text[1:].lstrip()
            item_indent = ind + len(text) - len(rest)
            if not rest:
                if self.i < len(self.tok) and self.tok[self.i][1] > ind:
                    items.append(self.block(self.tok[self.i][1]))
                else:
                    items.append(None)
            elif rest in BLOCK_STYLES:
                value, last_ln = self.block_scalar(ln, ind, rest)
                while self.i < len(self.tok) and self.tok[self.i][0] <= last_ln:
                    self.i += 1
                items.append(value)
            elif rest == "-" or rest.startswith("- ") or _split_key(rest) is not None:
                items.append(self.node_from_first_line(ln, item_indent, rest))
            else:
                if self.i < len(self.tok) and self.tok[self.i][1] > ind:
                    raise Error("unexpected indentation", self.tok[self.i][0])
                items.append(_scalar(rest, ln))
        return items

    def node_from_first_line(self, ln, ind, text):
        """Parse a node whose first line lives inside a ``- `` item."""
        if text == "-" or text.startswith("- "):
            return self.seq(ind, first=(ln, ind, text))
        kv = _split_key(text)
        if kv is not None:
            return self.map(ind, first=(ln, kv))
        if self.i < len(self.tok) and self.tok[self.i][1] > ind:
            raise Error("unexpected indentation", self.tok[self.i][0])
        return _scalar(text, ln)

    def block_scalar(self, key_ln, key_indent, style):
        """Collect a ``|`` or ``>`` scalar from the raw lines after ``key_ln``
        (1-based). Chomping indicators ``-`` and ``+`` are honored."""
        folded = style[0] == ">"
        seg = []
        j = key_ln
        while j < len(self.raw):
            line = self.raw[j]
            if line.strip() == "":
                seg.append((j + 1, None))
                j += 1
                continue
            ind = len(line) - len(line.lstrip(" "))
            if ind <= key_indent:
                break
            seg.append((j + 1, ind))
            j += 1
        trailing = 0
        while seg and seg[-1][1] is None:
            seg.pop()
            trailing += 1
        last_ln = seg[-1][0] if seg else key_ln
        if not seg:
            return "", last_ln
        mind = min(ind for _, ind in seg if ind is not None)
        body = [self.raw[n - 1][mind:] if ind is not None else "" for n, ind in seg]
        if folded:
            # Lines at the block indent fold to spaces; blank lines split
            # paragraphs and more-indented lines keep their line breaks.
            paras = [[]]
            for line, (_, ind) in zip(body, seg):
                if ind is None:
                    paras.append([])
                else:
                    paras[-1].append((line, ind))
            chunks = []
            for para in paras:
                buf = []
                for k, (line, ind) in enumerate(para):
                    sep = "" if k == 0 else (" " if para[k - 1][1] == mind and ind == mind else "\n")
                    buf.append(sep + line)
                chunks.append("".join(buf))
            text = "\n".join(chunks)
        else:
            text = "\n".join(body)
        if style.endswith("+"):
            text += "\n" * (trailing + 1)
        elif not style.endswith("-"):
            text += "\n"
        return text, last_ln


# --- dumping -----------------------------------------------------------------

def dump(obj):
    """Serialize a dict, list or scalar to the YAML subset ``load`` reads."""
    lines = []
    _emit(obj, 0, lines)
    return "\n".join(lines) + "\n"


def _emit(node, ind, lines):
    pad = " " * ind
    if isinstance(node, dict):
        if not node:
            lines.append(pad + "{}")
            return
        for k, v in node.items():
            key = _key_repr(k)
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}{key}:")
                _emit(v, ind + 2, lines)
            else:
                lines.append(f"{pad}{key}: {_scalar_repr(v)}")
    elif isinstance(node, list):
        if not node:
            lines.append(pad + "[]")
            return
        for item in node:
            if isinstance(item, (dict, list)) and item:
                sub = []
                _emit(item, ind + 2, sub)
                sub[0] = f"{pad}- {sub[0][ind + 2:]}"
                lines.extend(sub)
            else:
                lines.append(f"{pad}- {_scalar_repr(item)}")
    else:
        lines.append(pad + _scalar_repr(node))


__all__ = ["Error", "load", "dump"]
