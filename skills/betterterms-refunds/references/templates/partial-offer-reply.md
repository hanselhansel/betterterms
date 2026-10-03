# Template: partial offer reply

When to use: the merchant offered something below the target (a partial
refund, credit, or coupon) and the plan says to keep negotiating. Draft
action `send`.

Agent notes:

- `{quote:1}` renders the first amount from the inbound `amounts` list;
  confirm the index against the score output's `suggested_amounts`.
- If the offer is actually at or above target, do not use this template;
  ask the user to approve acceptance instead.
- A credit or coupon is a different remedy, not a smaller refund. Say so
  plainly when the user wants money back.

Template:

```text
Hello,

Thank you for the offer of {quote:1}. I appreciate it, though it does
not cover what happened: {fact:what-happened}

I am looking for the refund of {offer} to my original payment method,
in line with your policy. {fact:policy-quote}

I hope we can settle this directly. Please let me know if you can
approve it, or pass this to someone who can.

Thank you,
```
