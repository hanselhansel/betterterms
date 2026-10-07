"""Bounded linear scanners for the UserPromptSubmit hook.

Pure text scans with no IO and no btlib import: ``user_text`` and
``live_text`` read the Projects wake envelope, ``floor_hit`` is the
default-deny floor lookalike. The envelope reader is one pass of
``str.find`` -- each search starts where the last match ended -- and
the floor rule walks whitespace tokens once, so a pathological
prompt costs its length a small constant number of times.
"""

import re

# Floor is default deny: `bt` and `floor` adjacent, any whitespace
# and case. The payload rule lives in floor_hit.
_FLOOR_WORDS = re.compile(r"\bbt\s+floor\b", re.I)
# A case id (name-YYYYMMDD-xxxx) carries digits that are the id, not
# a typed number. Matched as a whole whitespace token: each token is
# examined once, and a token that only resembles an id glued inside
# longer text is not one -- its digits count toward the floor rule.
_CASE_ID_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*-\d{8}-[0-9a-f]{4}")
_TOKEN = re.compile(r"\S+")
# A word amount claims the walk-away without digits: the same forms
# btlib.wordlists.NUMBER_WORDS names plus the scale words. ``sixty``
# alone blocks; ordinary prose ("bt floor is set in the terminal")
# carries none of these and passes.
_FLOOR_WORD_AMOUNT = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred|thousand|million|billion|dozen|grand)\b",
    re.I,
)

# Attribute extraction never uses a `[\w-]+` regex: on a run of
# word/dash characters with no `="` inside, it would backtrack once
# per candidate position. ``_attrs`` anchors on `="` instead, walks
# the key back over the key-character run, and finds the closing
# quote with str.find -- one pass per pair, no rescanning.
_KEY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)
_ENTITIES = (
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&#39;", "'"),
    ("&quot;", '"'),
    ("&amp;", "&"),  # last, so &amp;lt; stays &lt;
)

_OPEN = "<message"
_CLOSE = "</message>"
_WORD_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)


def _unescape(text):
    for src, dst in _ENTITIES:
        text = text.replace(src, dst)
    return text


def _attrs(text):
    """The ``key="value"`` pairs of a tag's attribute run, same
    result as ``_ATTR.findall`` but linear: each ``="`` is found
    once, its key is the ``[\\w-]`` run that ends exactly at the
    ``=`` (an empty run is no pair and the scan continues), and the
    value ends at the next ``"``. An ``="`` whose value never closes
    ends the scan -- no pair can start inside a region with no quote.
    """
    pairs = []
    pos = 0
    while True:
        eq = text.find('="', pos)
        if eq < 0:
            return pairs
        k = eq
        while k > 0 and text[k - 1] in _KEY_CHARS:
            k -= 1
        if k == eq:
            pos = eq + 1
            continue
        v_end = text.find('"', eq + 2)
        if v_end < 0:
            return pairs
        pairs.append((text[k:eq], text[eq + 2 : v_end]))
        pos = v_end + 1


def _messages(prompt):
    """Yield ``(attrs, body_start, end, body)`` for each complete
    ``<message>`` element, in one pass.

    Same shape as ``<message\\b([^>]*)>(.*?)</message>`` in order:
    the attribute run ends at the first ``>`` and the body at the
    first literal ``</message>``. An opener that cannot complete --
    no ``>`` or no ``</message>`` left -- ends the scan, because
    nothing after it can complete either. That is what keeps the
    read linear where a lazy-regex retry would rescan the tail once
    per failed candidate.
    """
    pos = 0
    while True:
        start = prompt.find(_OPEN, pos)
        if start < 0:
            return
        attr_at = start + len(_OPEN)
        if (
            attr_at < len(prompt)
            and prompt[attr_at] in _WORD_CHARS
        ):
            pos = attr_at
            continue
        gt = prompt.find(">", attr_at)
        if gt < 0:
            return
        close = prompt.find(_CLOSE, gt + 1)
        if close < 0:
            return
        end = close + len(_CLOSE)
        yield prompt[attr_at:gt], gt + 1, end, prompt[gt + 1 : close]
        pos = end


def user_text(prompt):
    """The user's own text inside ``prompt``. A prompt counts as a
    Projects wake envelope only when its trimmed text starts with
    ``<wake`` and carries a ``<message`` element; then only the body
    of the ``<message>`` carrying both ``trigger="true"`` and
    ``from="human"`` counts (no human trigger: nothing counts). A
    ``<wake`` substring anywhere else, or a ``<wake`` opener with no
    ``<message>``, is the user's own words and the whole prompt is
    used."""
    t = prompt.lstrip()
    if not (t.startswith("<wake") and "<message" in t):
        return prompt
    for attrs, _start, _end, body in _messages(prompt):
        values = dict(_attrs(attrs))
        if (
            values.get("from") == "human"
            and values.get("trigger") == "true"
        ):
            return _unescape(body)
    return ""


def live_text(prompt):
    """Live text for the floor rule: the prompt minus the bodies of
    well-formed ``from="agent"`` elements. A human body stays in
    scope even when it is not the trigger: the envelope forwards it
    to the model, so a walk-away inside must still block."""
    parts, pos = [], 0
    for attrs, body_start, end, _body in _messages(prompt):
        head = attrs.rstrip()
        if head.endswith("/"):
            continue
        if dict(_attrs(head)).get("from") == "agent":
            parts.append(prompt[pos:body_start])
            pos = end
    parts.append(prompt[pos:])
    return "".join(parts)


def _case_id_spans(text):
    """The (start, end) of each whitespace token that is a case id."""
    for m in _TOKEN.finditer(text):
        if _CASE_ID_TOKEN.fullmatch(m.group(0)):
            yield m.span()


def floor_hit(text):
    """The one floor rule: ``bt`` and ``floor`` adjacent, plus a
    digit or a number word outside a case-id token, or any non-empty
    token after a case id -- a word amount like ``sixty two`` claims
    the walk-away too, with or without a case id and in any order."""
    m = _FLOOR_WORDS.search(text)
    if m is None:
        return False
    spans = list(_case_id_spans(text))
    for s, e in spans:
        if s >= m.end() and text[e:].strip():
            return True
    parts, pos = [], 0
    for s, e in spans:
        parts.append(text[pos:s])
        parts.append(" ")
        pos = e
    parts.append(text[pos:])
    scrubbed = "".join(parts)
    return bool(
        re.search(r"\d", scrubbed)
        or _FLOOR_WORD_AMOUNT.search(scrubbed)
    )
