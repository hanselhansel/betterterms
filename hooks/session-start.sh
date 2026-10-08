#!/bin/sh
# SessionStart hook for the betterterms plugin.
#
# The marker line tells the skills the typed `bt` commands are live,
# so it prints only after the prompt check AND its runtime actually
# load: a missing interpreter, a broken import, or a btlib that is
# not installed must not advertise commands that would reach the
# model unhandled. The preflight imports the modules the commands
# depend on; it never opens a case or a floor. With cases on disk
# the start pointer follows, and a remote session whose betterterms
# home sits under the ephemeral $HOME also gets the vanish warning,
# since those cases go away with the VM.
set -u

root="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"

if echo '{}' | "${PYTHON:-python3}" "$root/hooks/prompt_commands.py" >/dev/null 2>&1 \
&& BT_HOOKS="$root/hooks" "${PYTHON:-python3}" -c \
'import os, sys; sys.path.insert(0, os.environ["BT_HOOKS"]); import _btpath; _btpath.import_btlib(); from btlib import cases, gate, held, widgets' \
>/dev/null 2>&1; then
    echo "betterterms: typed bt commands are active in this session."
else
    echo "betterterms: the prompt check failed to run; typed bt commands are off and held drafts stay held. Repair or reinstall the plugin before approving them."
fi

home="${BETTERTERMS_HOME:-$HOME/.betterterms}"

if [ -d "$home/cases" ] \
    && [ -n "$(find "$home/cases" -mindepth 1 -maxdepth 1 -type d -print -quit 2>/dev/null)" ]; then
    if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
        case "$home" in
            "$HOME"|"$HOME"/*)
                echo "betterterms: cloud session; cases under $home vanish when the VM ends."
                ;;
        esac
    fi
    echo "betterterms is installed. Use the betterterms-start skill to begin or continue a negotiation."
fi
