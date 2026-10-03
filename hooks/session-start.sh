#!/bin/sh
# SessionStart hook for the betterterms plugin.
#
# Prints one line pointing the agent at the betterterms-start skill.
# In remote (cloud) sessions nothing is printed unless a case already
# exists under $BETTERTERMS_HOME/cases: a fresh cloud checkout has no
# state to resume and the pointer is noise there.
set -eu

if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
    home="${BETTERTERMS_HOME:-$HOME/.betterterms}"
    if [ ! -d "$home/cases" ] \
        || [ -z "$(find "$home/cases" -mindepth 1 -maxdepth 1 -type d -print -quit 2>/dev/null)" ]; then
        exit 0
    fi
fi

echo "betterterms is installed. Use the betterterms-start skill to begin or continue a negotiation."
