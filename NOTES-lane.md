# Lane R2 notes

Out-of-scope observations and follow-ups for other lanes or the
release owner. Nothing here was implemented.

## Interpretation choices (within R2 scope)

- "never_disclose items with letters block" was applied to the whole
  rendered message, not just quote spans: a listed term is never a
  coincidence, and the substring check is what the old review-tier
  code already computed. `test_gate.py`,
  `test_gate_hardening.py` never_disclose tests were updated from
  needs_approval to block to match.
- Verbatim quote strings are masked in `find.masked` like numeric
  quote outputs (they are guaranteed counterparty data). A non-ASCII
  or off-allowlist character inside a verbatim quote therefore does
  NOT route to review; it is the counterparty's own text, not the
  agent's. If that ever matters, scan `find.quote_spans` for the
  unusual-char check too.
- `<slot>` markers in templates are substituted with a stand-in word
  by the check (they are agent fill-ins, not literal output). This
  keeps the useful "you forgot a slot" failure mode: a literal `<`
  in a real draft still routes to review.

## For other lanes

- `templates/pack/references/templates/example.md` (the pack
  scaffold) is not under `skills/`, so templates-gate does not cover
  it. Cover it too if the scaffold counts as shipped wording.
- The eval lane may want cases for: verbatim string quotes, a
  lettered never_disclose item inside a quote, a negated commitment
  phrase ("won't take it"), and a ledger written by two concurrent
  processes.
- `gate.py` numbers its hard blocks 1-9; `SKILL.md` numbers its own
  list 1-10. They are separate lists, kept in sync by hand.
- `accept`-action templates (cancellations/accept-offer.md) are
  gated by the check as `send` drafts, which is stricter than their
  real path (`accept` always passes through `--approved`, where the
  review tier does not run). That is deliberate: the template text
  is held to the send standard anyway.
