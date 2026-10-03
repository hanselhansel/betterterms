# Template: follow-up after a live call (coach mode)

Use when: the user just had the pricing call and needs a written
recap that locks in what was said without agreeing to anything.
The counterparty's stated amounts enter through `{quote:n}`.

```text
Subject: Recap of our call

Hello,

Thank you for the time today. Confirming what I heard: the offer was
{quote:1} on the terms we discussed, and you asked for a decision by
our renewal date.

I am reviewing it against my budget and forecast and will reply as
promised. If anything above is off, please correct me.

Best,
```

Notes:

- `{quote:1}` renders the first amount from the inbound `amounts`
  list the agent extracted from the user's recap. Point the index at
  the quoted price, not at a term length or date.
- Coach mode gates every send to `needs_approval`; the user sends
  the final words.
