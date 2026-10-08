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
# A word amount claims the walk-away without digits. The word lists
# mirror btlib.wordlists verbatim -- inlined because this scanner
# must work with no runtime installed -- and the same matching rule:
# a lowercased letter run containing a number word or a scale stem
# counts even glued ("sixtytwo", "twok", "halfmillion",
# "thousandfold"), unless the whole run is a listed common English
# word ("often", "money"); the one- and two-letter scale
# abbreviations count only as whole tokens ("bt floor a mil", "k")
# because inside a run they are ordinary letters ("milk", "family").
_NUMBER_WORDS = frozenset(
    "zero one two three four five six seven eight nine ten eleven "
    "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen twenty thirty forty fifty sixty seventy eighty "
    "ninety dozen fifth ninth twelfth".split()
)
_NUMBER_WORD_EXCEPTIONS = frozenset(
    "abandoned alone antenna anyone artwork attend attendance "
    "attended attending attention attentive bitten bone bones clone "
    "commissioner commissioners competent component components "
    "consistency consistent consistently content contents done "
    "everyone existence extend extended extending extends extension "
    "extensions extensive extent forgotten freight frightened gone "
    "gotten headphones height heights honest honestly honey hormone "
    "hydrocodone indonesia indonesian intend intended intense "
    "intensity intensive intent intention intentionally jones leone "
    "liechtenstein lightweight listen listened listening lone lonely "
    "maintenance mentioned microphone milestone milestones monetary "
    "money network "
    "networking networks nintendo none nonetheless often oftentimes "
    "ones opponent opponents ozone patent patents persistent phone "
    "phoned phones phoning pioneer potential potentially "
    "practitioner practitioners prisoner prisoners retention "
    "ringtone ringtones sentence sentences softened someone soonest "
    "stationery stone stones superintendent telephone tenant tend "
    "tender tennessee tennis tension tent tenure threatened "
    "threatening tone toned toner tones weight weighted weights "
    "written zone zones".split()
)
_SCALE_WORD_STEMS = frozenset(
    "billion crore grand hundred lakh million quadrillion thousand "
    "trillion".split()
)
_SCALE_WORDS = frozenset(
    "hundred hundreds thousand thousands million millions billion "
    "billions trillion trillions quadrillion quadrillions lakh lakhs "
    "crore crores bn mm k m mil thou mn mln bln tn bil".split()
)
_LETTER_RUN = re.compile(r"[a-z]+")
# The gate's token shape: alphanumerics keeping interior
# apostrophes, so "i'll" is one token and "won't" is not "won".
_WORD_TOKEN = re.compile(r"[0-9A-Za-z]+(?:'[0-9A-Za-z]+)*")
# A possessive or contraction suffix hides the word behind it
# ("deal's", "k's"); "'t" alone never strips, so "won't" is "wo".
_SUFFIXES = ("'s", "'ll", "'re", "'ve", "'d", "'m", "n't")

# Attribute extraction never uses a `[\w-]+` regex: on a run of
# word/dash characters with no `="` inside, it would backtrack once
# per candidate position. ``_attrs`` anchors on `="` instead, walks
# the key back over the key-character run, and finds the closing
# quote with str.find -- one pass per pair, no rescanning. The key
# run is Unicode \w plus dash -- str.isalnum() is exactly \w minus
# the underscore -- so the key in <message éfrom="agent"> is éfrom,
# not from, and the body stays in floor scope.
def _key_char(c):
    return c.isalnum() or c in "_-"


_ENTITIES = (
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&#39;", "'"),
    ("&quot;", '"'),
    ("&amp;", "&"),  # last, so &amp;lt; stays &lt;
)

_OPEN = "<message"
_CLOSE = "</message>"


def _word_char(c):
    # Same Unicode boundary as <message\b: é is a word character,
    # so <messageé is not an element opener.
    return c.isalnum() or c == "_"


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
        while k > 0 and _key_char(text[k - 1]):
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
            and _word_char(prompt[attr_at])
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


# A numeral-style value ("LXII"): two or more Roman digits, caps
# only -- a lone "I" is a pronoun and lowercase runs are ordinary
# words, but an all-caps numeral readout is a malformed amount the
# default-deny path claims.
_ROMAN_TOKEN = re.compile(r"[IVXLCDM]{2,}")
# The longest supported scale word; membership checks below only
# ever need a form this short or shorter.
_SCALE_MAX = max(len(w) for w in _SCALE_WORDS)


def _is_scale_token(tok):
    """Whether ``tok`` names a scale word or abbreviation, possibly
    under a chain of contraction suffixes ("mil's" counts). One
    lowercase copy, then a walk of the trailing ``_SUFFIXES`` with
    ``str.endswith(suf, 0, end)``: no per-form allocation, so a
    pathological suffix chain costs its length once. Only a form at
    most ``_SCALE_MAX`` long can match, so slicing happens for a
    handful of short forms at the tail."""
    low = tok.lower()
    end = len(low)
    while True:
        if end <= _SCALE_MAX and low[:end] in _SCALE_WORDS:
            return True
        for suf in _SUFFIXES:
            if end > len(suf) and low.endswith(suf, 0, end):
                end -= len(suf)
                break
        else:
            return False


def _word_amount(text):
    """True when ``text`` carries a word amount the way the gate's
    review tier reads it: a lowercased letter run containing a
    number word or scale stem outside the listed exceptions
    ("sixtytwo", "two lakh", "twok" count), a token whose
    suffix-stripped forms hold a whole scale word or abbreviation
    ("mil", "thou", "bn"), or an all-caps numeral readout ("LXII").
    One pass per run and per token, no backtracking."""
    for run in _LETTER_RUN.findall(text.lower()):
        if run in _NUMBER_WORD_EXCEPTIONS:
            continue
        words = _NUMBER_WORDS | _SCALE_WORD_STEMS
        if any(w in run for w in words):
            return True
    for m in _WORD_TOKEN.finditer(text):
        tok = m.group(0)
        if _ROMAN_TOKEN.fullmatch(tok) or _is_scale_token(tok):
            return True
    return False


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
    return bool(re.search(r"\d", scrubbed) or _word_amount(scrubbed))
