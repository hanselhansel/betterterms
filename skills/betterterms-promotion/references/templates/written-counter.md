# Written counter with equal options

Use when the negotiation moves to email, or when the user prefers to
answer a stated offer in writing rather than live. Sends the plan's
equal options instead of a single demand. Option labels must match
`plan.yaml` exactly.

Draft fields:

- `action`: `send`
- `offer`: null (set it only when the counter is one number; then
  `{offer}` carries it)
- `period`: `year`
- `claims`: the fact ids the template renders

```text
Subject: Following up on compensation

Hi <name>,

Thank you for the offer and for the conversation. Based on my
results this year and the market data we discussed ({fact:f-market}),
I was hoping we could land closer to {target}.

A few shapes that all fit on my side:

- {option:level-plus-raise}: move to <target level> with the raise.
- {option:raise-now}: stay at the current level with the higher base.
- {option:title-plus-review}: the new title now, with a dated
  salary review.

Each of these fits. Which can we make happen?

Best,
```

Notes:

- List only the options the plan holds; drop a bullet rather than
  inventing one.
- `{fact:f-market}` renders the market-data fact the script already
  used. Swap in the case's real fact id.
- An offer equal to or better than the target goes to the user for
  an explicit accept; it is never accepted inside a counter email.
