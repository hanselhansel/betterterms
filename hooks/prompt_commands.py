#!/usr/bin/env python3
"""UserPromptSubmit hook: the typed ``bt ...`` commands (spec 6.8).

Reads each prompt before the model sees it. Only the user's own text
counts: inside a Projects wake envelope that is the ``<message>``
with ``trigger="true"`` and ``from="human"``; anywhere else the
whole prompt. A message whose trimmed text matches the grammar:

  bt approve <case_id> <hash8>   -> held approve, pass with a note
  bt reject  <case_id> <hash8>   -> held reject, pass with a note
  bt floor   <case_id> <amount>  -> case set-floor on stdin, then block
  bt terms   <case_id> target=<a> and/or alternative=<b> ->
                                  case set-terms, pass with a note

``bt floor`` always blocks, so the walk-away is never forwarded
to the model; its reason never carries the amount, and where the
host honors it the block output suppresses the submitted text. A
message that
only resembles a command still blocks, under two different rules.
Floor is default deny and runs first, at the shared layer: before
any command is handled, the live text is scanned for ``bt`` and
``floor`` adjacent (any whitespace, any case) plus a digit outside
a case-id token like ``name-YYYYMMDD-xxxx``, or any non-empty
token after a case id, digits or words. Live text is the prompt
minus the bodies of well-formed ``from="agent"`` message elements
only: a human body stays in scope, triggering or not, because a
wake envelope would otherwise forward a walk-away it carries to
the model. A hit always blocks: the floor write runs only when the
triggering message parses as a valid floor command, and nothing
passes through with a note. Approve, reject, and terms keep the
start-anchored rule: the trimmed user text starts with ``bt
<verb>`` (one leading backtick or slash allowed) plus the piece
the verb needs, a hex token of six or more characters for approve
and reject, ``=`` for terms. Everything else is prose and passes
to the model. The hook fails closed: unreadable input or a raising
command blocks, since the text may carry a walk-away.
"""

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _btpath
import _scan

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

# The hook reads the prompt once, bounded: a message past the cap is
# blocked rather than scanned partially (a floor payload could hide
# past the cut).
_MAX_PROMPT = 256 * 1024
# The other lookalikes count only at the start of the trimmed text,
# after at most one backtick or a leading slash. A `bt <verb>`
# mention inside prose is chat text, not a command attempt.
_LOOKALIKE = re.compile(r"[`/]?bt\s+(approve|reject|terms)\b", re.I)
_HEX_TOKEN = re.compile(r"\b[0-9a-f]{6,}\b", re.I)

# The envelope readers and the default-deny floor scan live in
# _scan.py: single-pass str.find message parsing, `="-anchored
# attribute reads and one-pass token matching, no runtime
# dependency.
user_text = _scan.user_text
_live_text = _scan.live_text
_floor_hit = _scan.floor_hit


def _terms_args(pairs_text):
    """The ``key=value`` tail of a ``bt terms`` message: each key at
    most once, at least one of ``target`` or ``alternative``, no
    other keys. Anything else returns None and lands in usage."""
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
    """The command a whole trimmed message names, or None: ``verb``
    and ``case_id`` plus ``hash8``, ``amount`` or the terms pair."""
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
    """The verb a non-command message resembles, or None. Approve,
    reject, and terms count only at the start of the trimmed text
    (one leading backtick or slash allowed) plus their marker piece:
    a hash-like token for approve and reject, ``=`` for terms.
    ``_floor_hit`` runs on the live text before this point."""
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


def _block(reason, suppress=False):
    out = {"decision": "block", "reason": reason}
    if suppress:
        # Where the host honors the field, the block message does
        # not carry the submitted prompt's text. Local transcript
        # and history files still record it, which is why the
        # reason itself never echoes the amount.
        out["hookSpecificOutput"] = {
            "hookEventName": "UserPromptSubmit",
            "suppressOriginalPrompt": True,
        }
    _emit(out)


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
    """Run bt.py, returning (exit code, parsed stdout, error text):
    stdout's ``error``, else the last stderr line, else the code."""
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
    reason never names the amount and the original prompt is
    suppressed where the host supports it."""
    from btlib import BtError, cli_extra

    try:
        value = cli_extra.parse_amount(raw)
    except BtError:
        _block(
            "betterterms: bad amount; use a number like 62 or 62.50",
            suppress=True,
        )
        return
    code, _out, err = _run_bt(
        ["case", "set-floor", case_id], stdin_text=f"{value:.2f}\n"
    )
    if code != 0:
        _block(f"betterterms: {err}", suppress=True)
        return
    _block(
        f"betterterms: walk-away saved for {case_id}; "
        "this prompt was not sent to the model.",
        suppress=True,
    )


def approve_command(case_id):
    """The gate command the approve note names, runnable as printed:
    ``--inbound`` when the file exists, ``--approved`` last."""
    from btlib import cases

    d = cases.case_dir(case_id)
    argv = [
        "python3",
        str(_btpath.bt_path()),
        "gate",
        case_id,
        "--draft",
        str(d / "draft.yaml"),
    ]
    if (d / "inbound.yaml").is_file():
        argv += ["--inbound", str(d / "inbound.yaml")]
    argv.append("--approved")
    return shlex.join(argv)


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
        gate = approve_command(case_id)
        _pass(
            f"betterterms: the user approved draft {short} for "
            f"{case_id}. Run `{gate}` once, then "
            "send only on a pass verdict: the rendered text it "
            "returns goes verbatim as its own argument, nothing "
            "added. A needs_approval or block verdict sends nothing "
            "and shows the user the reasons. The marker spends "
            "once: a second --approved run holds the draft again."
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
    # Floor prompts may carry the walk-away: every failure on that
    # path suppresses the original where the host supports it.
    suppress = cmd["verb"] == "floor"
    try:
        _btpath.import_btlib()
        from btlib import cases
    except Exception:
        _block(
            "betterterms: cannot reach the bt.py runtime",
            suppress=suppress,
        )
        return
    cid = cmd["case_id"]
    if not cases.CASE_ID_RE.fullmatch(cid) or not cases.case_dir(
        cid
    ).is_dir():
        # A floor prompt's case field may be part of the payload
        # (`bt floor sixty two`), so that path never echoes it.
        _block(
            "betterterms: no such case"
            if suppress
            else f"betterterms: no case {cid}",
            suppress=suppress,
        )
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
        raw_in = sys.stdin.read(_MAX_PROMPT + 1)
        if len(raw_in) > _MAX_PROMPT:
            _block(
                "betterterms: the prompt is too large to check",
                suppress=True,
            )
            return 0
        event = json.loads(raw_in or "{}")
        raw = str(event.get("prompt") or "")
        text = user_text(raw)
        cmd = parse(text)
        # Fail-closed backstop before any command is handled: the
        # floor rule scans the live text. A hit always blocks -- the
        # write runs only when the trigger is itself a floor command.
        if _floor_hit(_live_text(raw)):
            if cmd is not None and cmd["verb"] == "floor":
                _handle(cmd)
            else:
                _block(
                    f"betterterms: expected '{USAGE['floor']}'",
                    suppress=True,
                )
            return 0
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
