#!/bin/sh
# SessionStart hook for the betterterms plugin.
#
# The marker line prints whenever this hook runs, plugin or vendored:
# the skills offer typed `bt` commands and widgets only when they see
# it in context, so it must print even before any case exists. With
# cases on disk the start pointer follows, and a remote session whose
# betterterms home sits under the ephemeral $HOME also gets the vanish
# warning, since those cases go away with the VM.
set -eu

echo "betterterms: typed bt commands are active in this session."

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
