# Lane 3.1 notes (evals harness)

For the orchestrator. Nothing here was implemented because the files are
outside this lane's list.

## Observations

1. **Gate blocks quoting the counterparty's numbers.** Gate rule 7
   allows only the offer, option/ladder values, the target, and amounts
   inside fact texts. A draft that restates the inbound offer (for
   example "your $11,000 quote is still above Parallax") blocks as an
   untraced number. If restating their price should be legal, the
   inbound offer could join the allowed set in `btlib/gate.py`.
2. **Chat prompts land as JSON text for claude-agent-sdk.** promptfoo
   renders a python prompt function's list-of-messages result with
   `JSON.stringify`, and `anthropic:claude-agent-sdk` sends that string
   to `query()` as the user prompt. The "system" content therefore
   arrives inside the user turn, not in a real system slot. If a real
   system prompt is wanted later, `get_prompt` can return
   `{"prompt": <user text>, "config": {"custom_system_prompt": <text>}}`;
   the provider maps `custom_system_prompt` to the SDK's systemPrompt
   option. Left as chat messages per the brief.
3. **Holdout path.** `scripts/eval --holdout` looks for
   `$BETTERTERMS_HOLDOUT/promptfooconfig.yaml` (default
   `~/.betterterms-holdout/`). `evals/holdout/` is already in
   .gitignore; a symlink there can point at the real folder so the tree
   stays self-contained.
