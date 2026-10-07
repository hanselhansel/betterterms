"""Owned-hook detection and migration for vendor-into-repo.

Everything here answers one question: is a settings.json hook
command THIS plugin's vendored script, invoked as a command --
never a similarly named custom hook, a path passed as data, or a
mention inside quotes. ``migrate_problems`` names the shapes a safe
rewrite cannot handle (an owned invocation on either side of a
single ``|``), and ``migrate_prompt`` rewires the rest: the old
unguarded prompt_commands.py invocation becomes the guarded launch,
and once the guarded command is registered each remaining owned
invocation becomes the ``true`` no-op so unrelated commands inside
the same compound command keep their order, quoting and fields.
"""

import re

# Exact owned paths only, never a shared prefix: an old vendored
# prompt_commands.py command is this plugin's hook and is migrated
# to the guarded launcher, while a similarly named custom hook
# under the same directory is left untouched.
PROMPT_OLD = ".claude/betterterms/hooks/prompt_commands.py"
PROMPT_NEW = ".claude/betterterms/hooks/prompt-guard.sh"
HOOK_PATHS = {
    "UserPromptSubmit": PROMPT_NEW,
    "SessionStart": ".claude/betterterms/hooks/session-start.sh",
}
HOOK_COMMANDS = {
    "UserPromptSubmit": (
        'bash "$CLAUDE_PROJECT_DIR/.claude/betterterms/'
        'hooks/prompt-guard.sh"'
    ),
    "SessionStart": (
        'bash "$CLAUDE_PROJECT_DIR/.claude/betterterms/hooks/'
        'session-start.sh"'
    ),
}


def _call_re(path):
    """Match an *invocation* of the owned script ``path``: lead,
    optional ``env`` assignments and interpreter, then a token whose
    final segment is exactly the owned path (any directory prefix
    allowed). A ``-custom`` suffix, an ``x.claude`` directory, or a
    mention as data never matches."""
    return re.compile(
        r"(?P<lead>^|[;&|])\s*"
        r"(?:env\s+[^\s;|&()=]+=[^\s;|&()]+\s+)*"
        r"(?:(?:python3?|bash|sh|exec)\s+)?"
        r"[\"']?(?:[^\"'\s;|&()]*?/)?"
        + re.escape(path)
        + r"[\"']?(?=\s|$|[;&|])"
    )


_CALL_RES = {
    path: _call_re(path) for path in HOOK_PATHS.values()
}
_CALL_RES[PROMPT_OLD] = _call_re(PROMPT_OLD)


# A quoted span, the tail of an unterminated quote, or an escaped
# char is data, never shell syntax: no ``;`` ``&`` ``|`` lead there.
_QUOTED = re.compile(r"'[^']*('|$)|\"(?:\\.|[^\"\\])*(\"|$)|\\.")


def _quoted_mask(command):
    """A bytearray marking quoted or escaped spans: a ``;`` ``&``
    ``|`` inside one is data, never shell syntax."""
    mask = bytearray(len(command))
    for q in _QUOTED.finditer(command):
        mask[q.start() : q.end()] = b"\1" * (q.end() - q.start())
    return mask


def _shell_mask(command):
    """bytearray marking quoted, escaped or comment spans: chars
    there are data, never shell syntax. An unquoted, unescaped
    ``#`` at a word start -- command start, after whitespace, or
    after an unquoted ``;`` ``&`` ``|`` ``(`` ``)`` ``<`` ``>`` --
    comments out the rest of the line, so an owned path mentioned
    there was never invoked. A ``#`` mid-word (``a#b``) or right
    after a quoted word stays literal."""
    mask = _quoted_mask(command)
    i, n = 0, len(command)
    while i < n:
        if command[i] == "#" and not mask[i] and (
            i == 0
            or command[i - 1] in " \t\n"
            or (command[i - 1] in ";&|()<>" and not mask[i - 1])
        ):
            end = command.find("\n", i + 1)
            if end < 0:
                end = n
            mask[i:end] = b"\1" * (end - i)
            i = end
        else:
            i += 1
    return mask


def _call_match(command, path, pos=0):
    """The ``_call_re`` invocation match at or after ``pos``, or
    None when the owned path appears only as data: the ``^`` or
    ``;`` ``&`` ``|`` lead must sit outside quotes, unescaped, and
    outside a shell comment (``echo setup # ; bash <path>`` is a
    comment, not an invocation)."""
    mask = _shell_mask(command)
    for m in _CALL_RES[path].finditer(command, pos):
        if not m.group("lead") or not mask[m.start("lead")]:
            return m
    return None


def entry_hooks(entry):
    """An entry's hooks list, or () for a shape the merge skips."""
    hooks = entry.get("hooks") if isinstance(entry, dict) else None
    return hooks if isinstance(hooks, list) else ()


def has_hook(entries, path):
    """Whether any entry's hooks already invoke the vendored script
    at ``path``, whatever the entry's other fields."""
    return any(
        isinstance(h, dict)
        and _call_match(str(h.get("command", "")), path) is not None
        for entry in entries
        for h in entry_hooks(entry)
    )


def hook_entry(event):
    """The settings.json hooks entry for one event."""
    hook = {"type": "command", "command": HOOK_COMMANDS[event]}
    if event == "UserPromptSubmit":
        hook["timeout"] = 10
    entry = {"hooks": [hook]}
    if event == "SessionStart":
        entry["matcher"] = "startup|resume|clear|compact"
    return entry


def _pipe_to_right(cmd, m):
    """Whether the owned invocation's stream feeds a single ``|``.
    The invocation's args, flags and redirects run to the next
    ``;`` ``&&`` ``||`` lone ``&`` or text end -- a ``|`` anywhere
    in that extent still pipes it (``old --flag | cat``, ``old >
    out | cat``). ``>&fd`` is a redirect, not a separator; a
    ``|`` inside a shell comment is data, not a pipe."""
    mask = _shell_mask(cmd)
    i, n = m.end(), len(cmd)
    while i < n:
        if mask[i]:
            i += 1
            continue
        c = cmd[i]
        if c == "|":
            left = i > 0 and cmd[i - 1] == "|" and not mask[i - 1]
            right = i + 1 < n and cmd[i + 1] == "|" and not mask[i + 1]
            return not (left or right)
        if c == "&":
            if i > 0 and cmd[i - 1] == ">" and not mask[i - 1]:
                i += 1
                continue
            if i + 1 < n and cmd[i + 1] == ">":
                i += 2  # ``&>`` redirects both streams
                continue
            return False
        if c == ";":
            return False
        i += 1
    return False


def pipe_adjacent(cmd, m):
    """Whether the owned invocation at match ``m`` sits on either
    side of a single ``|``: a ``||`` lead is logical-or, not a
    pipe, and a ``|`` inside quotes or a comment was already
    excluded by _call_match."""
    lead = cmd[m.start("lead") : m.end("lead")]
    if lead == "|":
        prev = m.start("lead") - 1
        if prev < 0 or cmd[prev] != "|" or _shell_mask(cmd)[prev]:
            return True
    return _pipe_to_right(cmd, m)


def migrate_problems(entries):
    """Refusal list for commands the merge must not touch: an owned
    prompt_commands.py invocation on either side of a single ``|``.
    Migrated, the guarded command's block exit would sit mid-pipe
    and be masked by the downstream command; neutralized, the
    neighbour's stream would silently change. The user rewires
    these by hand."""
    problems = []
    for entry in entries:
        for h in entry_hooks(entry):
            if not isinstance(h, dict):
                continue
            cmd = str(h.get("command", ""))
            pos = 0
            while True:
                m = _call_match(cmd, PROMPT_OLD, pos)
                if m is None:
                    break
                if pipe_adjacent(cmd, m):
                    problems.append(
                        "piped owned prompt hook cannot be migrated "
                        f"safely: {cmd!r}"
                    )
                    break
                pos = m.end()
    return problems


def neutralize_owned(cmd):
    """``cmd`` with every owned prompt_commands.py invocation
    replaced by the ``true`` no-op. A pipe neighbour feeds a stream
    the no-op cannot reproduce, so a pipe-adjacent match stops the
    walk instead -- migrate_problems refuses those commands before
    the merge runs, so none reaches this point."""
    while True:
        m = _call_match(cmd, PROMPT_OLD)
        if m is None or pipe_adjacent(cmd, m):
            return cmd
        cmd = cmd[: m.end("lead")] + " true" + cmd[m.end() :]


def migrate_prompt(entries):
    """Rewire this plugin's owned unguarded prompt hook in place.
    The old prompt_commands.py invocation becomes the guarded
    command, preserving any command around it; once the guarded
    command is registered each remaining owned invocation becomes
    ``true`` (a bare ``true`` entry is dropped) so the rest of a
    compound command survives. A pipe-adjacent invocation is left
    untouched -- migrate_problems refuses it first. Other commands
    and fields are kept. Returns True when anything changed."""
    have_new = has_hook(entries, PROMPT_NEW)
    migrated = False
    changed = False
    for entry in entries:
        hooks = entry_hooks(entry)
        if not hooks:
            continue
        kept = []
        for h in hooks:
            cmd = str(h.get("command", "")) if isinstance(h, dict) else ""
            m = _call_match(cmd, PROMPT_OLD)
            if m is None or pipe_adjacent(cmd, m):
                kept.append(h)
                continue
            changed = True
            if not (have_new or migrated):
                h["command"] = neutralize_owned(
                    cmd[: m.end("lead")]
                    + (" " if m.end("lead") else "")
                    + HOOK_COMMANDS["UserPromptSubmit"]
                    + cmd[m.end() :]
                )
                migrated = True
                kept.append(h)
                continue
            new_cmd = neutralize_owned(cmd)
            if new_cmd.strip() != "true":
                h["command"] = new_cmd
                kept.append(h)
        hooks[:] = kept
    return changed
