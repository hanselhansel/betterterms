# Trust levels

Every source record carries `trust`. A claim rests on the highest level
that supports it; a contradiction between levels resolves toward the
higher one.

| Level | Meaning | May support |
|---|---|---|
| `official` | The counterparty's own published policy, terms, or pricing page | Claims quoted back to the counterparty |
| `regulator` | Statutes, regulator rules, consumer agency guidance | The user's rights in their jurisdiction |
| `press` | News reporting and named review sites | Market context and dated public claims |
| `forum` | First-hand reports: Reddit, X, community forums | Tactics to try; never stated as fact |

## Rules

- Official policy first. A forum report that contradicts published
  policy is a lead to verify, not a fact.
- Forum reports guide tactics ("ask for the retention desk") but are
  never asserted to the counterparty: "people say you always discount"
  is not a claim a draft may make.
- When a reply contradicts the published policy, quote the policy back.
- Re-check a record older than 90 days before relying on it:

  `python3 ../betterterms-guardrails/scripts/bt.py source stale <case_id> --days 90`
