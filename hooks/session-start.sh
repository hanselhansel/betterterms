#!/bin/sh
# SessionStart hook for the betterterms plugin.
#
# In remote (cloud) sessions a $BETTERTERMS_HOME under the ephemeral
# $HOME loses its cases when the VM ends, so a warning line prints
# first. Both lines wait on there being something to say: in a cloud
# session with no cases yet there is nothing to lose and nothing to
# resume, so the hook stays silent.
set -eu

home="${BETTERTERMS_HOME:-$HOME/.betterterms}"

if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
    if [ ! -d "$home/cases" ] \
        || [ -z "$(find "$home/cases" -mindepth 1 -maxdepth 1 -type d -print -quit 2>/dev/null)" ]; then
        exit 0
    fi
    case "$home" in
        "$HOME"|"$HOME"/*)
            echo "betterterms: cloud session; cases under $home vanish when the VM ends."
            ;;
    esac
fi

echo "betterterms is installed. Use the betterterms-start skill to begin or continue a negotiation."
