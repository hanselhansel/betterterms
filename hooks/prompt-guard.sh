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

# A caller override may only shorten the wait, never stretch it to
# or past the host's 10s forward timeout. Only a literal 1-8 counts:
# anything longer, non-numeric or zero falls back to the default.
# A glob test, not integer compare -- a value past the shell's
# integer width would error out of the comparison yet be kept.
deadline="${BT_HOOK_DEADLINE:-8}"
case "$deadline" in [1-8]) ;; *) deadline=8 ;; esac

block() {
  printf '%s\n' \
    '{"decision":"block","reason":"betterterms: the prompt check could not run"}'
  exit 2
}

tmp="$(mktemp "${TMPDIR:-/tmp}/bt-prompt-hook.XXXXXX")" || block
trap 'rm -f "$tmp"' EXIT

killtree() {
  # Descendants first, then the pid itself: a timed-out check must
  # not leave its own child (a bt.py approve or set-floor write)
  # running to finish after the block already reported failure.
  # pgrep -P walks only owned children, never a name-wide pkill.
  for _c in $(pgrep -P "$1" 2>/dev/null); do
    killtree "$_c"
  done
  kill -9 "$1" 2>/dev/null
}

# A background job gets /dev/null on stdin in POSIX shells unless an
# earlier descriptor is redirected in, so the event reaches the check
# through a saved fd, not the implicit empty stream.
mypid=$$
exec 3<&0
"${PYTHON:-python3}" "$root/hooks/prompt_commands.py" <&3 >"$tmp" 2>/dev/null &
pid=$!
# Watchdog: kill the check's whole tree once the deadline passes.
# Its fds are detached -- a background job would otherwise hold the
# caller's output pipe and saved event descriptor open for the full
# sleep, stalling a captured-output read until the deadline even
# when the check finished in milliseconds. The ppid check proves the
# pid is still this shell's live child before any kill, so a
# recycled pid number can never take an unrelated process down.
( sleep "$deadline"
  [ "$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')" = "$mypid" ] \
    && killtree "$pid"
) </dev/null >/dev/null 2>&1 3<&- &
watcher=$!
wait "$pid" 2>/dev/null
status=$?
# Cancel the pending kill: the sleep is the watcher's own child,
# so the same parent-scoped walk covers it.
killtree "$watcher"
wait "$watcher" 2>/dev/null

# A nonzero, killed or timed-out check blocks; its own output decides
# only on a clean exit.
[ "$status" -eq 0 ] || block
out="$(cat "$tmp" 2>/dev/null)"
[ -n "$out" ] && printf '%s\n' "$out"
exit 0
