# Template: policy pushback

When to use: the merchant denied the refund in a way that contradicts
their published policy. Draft action `send`.

Agent notes:

- `{fact:policy-quote}` must point at the fact that holds the policy
  text verbatim from its source record.
- Keep the tone warm. The policy does the work; do not argue past it.
- Pass `--inbound` to the gate so `{quote:n}` resolves if you cite their
  offer back.

Template:

```text
Hello,

Thank you for looking into this. Your published policy says:
{fact:policy-quote}

My request fits that policy. {fact:what-happened} I would like the
refund of {offer} to my original payment method, as the policy
describes.

If a specialist or supervisor needs to review this, please pass it
along. I am glad to send any other records that would help.

Thank you,
```
