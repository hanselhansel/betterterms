#!/usr/bin/env python3
"""UserPromptSubmit hook: the typed ``bt ...`` commands (spec 6.8).

Reads each prompt before the model sees it. Only the user's own text
counts: inside a Projects wake envelope that is the ``<message>``
element with ``trigger="true"`` and ``from="human"``; anywhere else
the whole prompt. A message whose whole trimmed text matches the
grammar is handled here:

  bt approve <case_id> <hash8>   -> held approve, pass with a note
  bt reject  <case_id> <hash8>   -> held reject, pass with a note
  bt floor   <case_id> <amount>  -> case set-floor on stdin, then block
  bt terms   <case_id> target=<a> and/or alternative=<b> ->
                                  case set-terms, pass with a note

``bt floor`` always blocks, so the walk-away is never forwarded to
the model; its reason never carries the amount. A message that only
resembles a command still blocks, under two different rules. Floor
is default deny: the words ``bt`` and ``floor`` adjacent -- any
whitespace, any case -- anywhere in the message, on any line and
after any prefix or markdown, plus any digit in the message, blocks
with the usage line. Approve, reject, and terms keep the
start-anchored rule: the trimmed text starts with ``bt <verb>`` --
one leading backtick or a leading slash allowed -- and carries the
piece the verb needs, a hex token of six or more characters for
approve and reject, ``=`` for terms. Everything else is prose and
passes to the model. The hook fails closed: input it cannot read,
or a command that raises, blocks instead of passing through,
because the text may carry a walk-away.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _btpath

USAGE = {
    "approve": "bt approve <case> <hash8>",
    "reject": "bt reject <case> <hash8>",
    "floor": "bt floor <case> <amount>",
    "terms": (
        "bt terms <case> target=<amount> and/or "
        "alternative=<amount>"
    ),
}

_GRAMMAR = (
    ("approve", re.compile(r"bt\s+approve\s+(\S+)\s+(\S+)", re.I)),
    ("reject", re.compile(r"bt\s+reject\s+(\S+)\s+(\S+)", re.I)),
    ("floor", re.compile(r"bt\s+floor\s+(\S+)\s+(\S+)", re.I)),
    # The tail is key=value pairs; _terms_args enforces the keys.
    (
        "terms",
        re.compile(r"bt\s+terms\s+(\S+)((?:\s+\w+=\S+)+)", re.I),
    ),
)

_TERMS_KV = re.compile(r"(\w+)=(\S+)")
_TERMS_KEYS = ("target", "alternative")

# Floor is default deny: the words `bt` and `floor` adjacent, any
# whitespace and any case, anywhere in the message. The digit check
# lives in _lookalike_verb; `bt floor` talk with no number in it is
# prose about the command.
_FLOOR_WORDS = re.compile(r"\bbt\s+floor\b", re.I)
# The other lookalikes count only at the start of the trimmed text,
# after at most one backtick or a leading slash. A `bt <verb>`
# mention inside prose is chat text, not a command attempt.
_LOOKALIKE = re.compile(r"[`/]?bt\s+(approve|reject|terms)\b", re.I)
_HEX_TOKEN = re.compile(r"\b[0-9a-f]{6,}\b", re.I)
_MESSAGE = re.compile(r"<message\b([^>]*)>(.*?)</message>", re.DOTALL)
_ATTR = re.compile(r'([\w-]+)="([^"]*)"')
_ENTITIES = (
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&#39;", "'"),
    ("&quot;", '"'),
    ("&amp;", "&"),  # last, so &amp;lt; stays &lt;
)


def _unescape(text):
    for src, dst in _ENTITIES:
        text = text.replace(src, dst)
    return text


def user_text(prompt):
    """The user's own text inside ``prompt``. A Projects wake envelope
    contributes only the body of the ``<message>`` carrying both
    ``trigger="true"`` and ``from="human"``; a prompt with no ``<wake``
    is used whole. An envelope with no human trigger contributes
    nothing at all, so agent text can never become a command."""
    if "<wake" not in prompt:
        return prompt
    for m in _MESSAGE.finditer(prompt):
        attrs = dict(_ATTR.findall(m.group(1)))
        if (
            attrs.get("from") == "human"
            and attrs.get("trigger") == "true"
        ):
            return _unescape(m.group(2))
    return ""


def _terms_args(pairs_text):
    """The ``key=value`` tail of a ``bt terms`` message: each key at
    most once, at least one of ``target`` or ``alternative`` present,
    no other keys. Anything else returns None, which lands the line
    in the usage block."""
    pairs = _TERMS_KV.findall(pairs_text)
    keys = [k.lower() for k, _v in pairs]
    if (
        not pairs
        or len(set(keys)) != len(keys)
        or any(k not in _TERMS_KEYS for k in keys)
    ):
        return None
    return {
        key: dict((k.lower(), v) for k, v in pairs).get(key)
        for key in _TERMS_KEYS
    }


def parse(text):
    """The command a whole trimmed message names, or None. Returns a
    dict with ``verb`` and ``case_id`` plus ``hash8``, ``amount`` or
    ``target``/``alternative`` depending on the verb."""
    t = text.strip()
    for verb, rx in _GRAMMAR:
        m = rx.fullmatch(t)
        if not m:
            continue
        out = {"verb": verb, "case_id": m.group(1)}
        if verb in ("approve", "reject"):
            out["hash8"] = m.group(2)
        elif verb == "floor":
            out["amount"] = m.group(2)
        else:
            args = _terms_args(m.group(2))
            if args is None:
                return None
            out.update(args)
        return out
    return None


def _lookalike_verb(text):
    """The verb a non-command message resembles, or None. Floor runs
    first and searches the whole message: ``bt`` and ``floor``
    adjacent plus any digit claims to set the walk-away no matter
    what precedes it. Approve, reject, and terms count only at the
    start of the trimmed text -- one leading backtick or a leading
    slash allowed -- and still need their marker piece: a hash-like
    token for approve and reject, ``=`` for terms. Anything else is
    prose."""
    if _FLOOR_WORDS.search(text) and re.search(r"\d", text):
        return "floor"
    t = text.strip()
    m = _LOOKALIKE.match(t)
    if m is None:
        return None
    verb = m.group(1).lower()
    if verb in ("approve", "reject"):
        return verb if _HEX_TOKEN.search(t) else None
    return verb if "=" in t else None


def _emit(obj):
    print(json.dumps(obj))


def _block(reason):
    _emit({"decision": "block", "reason": reason})


def _pass(note):
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": note,
            }
        }
    )


def _run_bt(args, stdin_text=None):
    """Run bt.py, returning (exit code, parsed stdout, error text).
    The error text is stdout's ``error`` field, else the last stderr
    line, else the exit code."""
    proc = subprocess.run(
        [sys.executable, str(_btpath.bt_path()), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        # The hook's own budget is 10s; a wedged bt.py must still
        # fail closed inside it.
        timeout=7,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = {}
    err = out.get("error")
    if not err:
        lines = proc.stderr.strip().splitlines()
        err = lines[-1] if lines else f"bt.py exited {proc.returncode}"
    return proc.returncode, out, err


def _floor(case_id, raw):
    """Write the walk-away through stdin, then block. The block
    reason never names the amount."""
    from btlib import BtError, cli_extra

    try:
        value = cli_extra.parse_amount(raw)
    except BtError:
        _block(
            "betterterms: bad amount; use a number like 62 or 62.50"
        )
        return
    code, _out, err = _run_bt(
        ["case", "set-floor", case_id], stdin_text=f"{value:.2f}\n"
    )
    if code != 0:
        _block(f"betterterms: {err}")
        return
    _block(
        f"betterterms: walk-away saved for {case_id}; "
        "this prompt was not sent to the model."
    )


def _held(verb, case_id, hash8):
    h = hash8.lower()
    if not re.fullmatch(r"[0-9a-f]{8,64}", h):
        _block("betterterms: expected a draft hash prefix (8+ hex)")
        return
    code, out, err = _run_bt(["held", verb, case_id, h])
    if code != 0:
        _block(f"betterterms: {err}")
        return
    short = str(out.get("hash") or h)[:8]
    if verb == "approve":
        _pass(
            f"betterterms: the user approved draft {short} for "
            f"{case_id}. Run `bt.py gate {case_id} --approved` once, "
            "then send the rendered text it returns verbatim as its "
            "own argument, nothing added. With betterterms-mod "
            "loaded an extra gate run is harmless: the mod's send "
            "check re-arms the marker."
        )
    else:
        _pass(
            f"betterterms: the user rejected draft {short} for "
            f"{case_id}. Do not send it."
        )


def _terms(case_id, target, alternative):
    args = ["case", "set-terms", case_id]
    parts = []
    if target is not None:
        args += ["--target", target]
        parts.append(f"target {target}")
    if alternative is not None:
        args += ["--alternative", alternative]
        parts.append(f"best alternative {alternative}")
    code, _out, err = _run_bt(args)
    if code != 0:
        _block(f"betterterms: {err}")
        return
    _pass(
        f"betterterms: the user updated terms for {case_id}: "
        f"{', '.join(parts)}."
    )


def _handle(cmd):
    try:
        _btpath.import_btlib()
        from btlib import cases
    except Exception:
        _block("betterterms: cannot reach the bt.py runtime")
        return
    cid = cmd["case_id"]
    if not cases.CASE_ID_RE.fullmatch(cid) or not cases.case_dir(
        cid
    ).is_dir():
        _block(f"betterterms: no case {cid}")
        return
    verb = cmd["verb"]
    if verb == "floor":
        _floor(cid, cmd["amount"])
    elif verb in ("approve", "reject"):
        _held(verb, cid, cmd["hash8"])
    else:
        _terms(cid, cmd["target"], cmd["alternative"])


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        text = user_text(str(event.get("prompt") or ""))
        cmd = parse(text)
        if cmd is not None:
            _handle(cmd)
            return 0
        lookalike = _lookalike_verb(text)
        if lookalike is not None:
            _block(f"betterterms: expected '{USAGE[lookalike]}'")
    except Exception:
        # Fail closed: a prompt this hook cannot read or handle may
        # carry a walk-away, so it must never fall through to the
        # model.
        _block("betterterms: the prompt check failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
