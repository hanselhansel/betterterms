#!/bin/sh
# UserPromptSubmit launcher: fail closed when the Python check cannot
# run or cannot finish. The configured host timeout only discards a
# timed-out hook's output and forwards the prompt, so the check runs
# under its own deadline: a hung interpreter, import, read or child
# process is killed comfortably before the host would forward the
# prompt unhandled. The emitted block is static and carries nothing
# from the prompt.
set -u

root="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
deadline="${BT_HOOK_DEADLINE:-8}"

block() {
  printf '%s\n' \
    '{"decision":"block","reason":"betterterms: the prompt check could not run"}'
  exit 2
}

tmp="$(mktemp "${TMPDIR:-/tmp}/bt-prompt-hook.XXXXXX")" || block
trap 'rm -f "$tmp"' EXIT

# A background job gets /dev/null on stdin in POSIX shells unless an
# earlier descriptor is redirected in, so the event reaches the check
# through a saved fd, not the implicit empty stream.
exec 3<&0
"${PYTHON:-python3}" "$root/hooks/prompt_commands.py" <&3 >"$tmp" 2>/dev/null &
pid=$!
# Watchdog: kill the check once the deadline passes; killing this
# subshell when the check exits cancels the pending kill. An orphaned
# sleep simply wakes to no signal and exits.
( sleep "$deadline"; kill -9 "$pid" ) 2>/dev/null &
watcher=$!
wait "$pid" 2>/dev/null
status=$?
kill "$watcher" 2>/dev/null
wait "$watcher" 2>/dev/null

# A nonzero, killed or timed-out check blocks; its own output decides
# only on a clean exit.
[ "$status" -eq 0 ] || block
out="$(cat "$tmp" 2>/dev/null)"
[ -n "$out" ] && printf '%s\n' "$out"
exit 0
