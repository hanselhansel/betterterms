# Template: opening request

When to use: the first written message to the merchant. Draft action
`send`.

Agent notes:

- Fill `{fact:...}` placeholders only with ids that exist in
  `plan.yaml` facts (order summary, what happened, evidence list).
- `{offer}` renders the planned ask; for a full refund it equals the
  target.
- Adjust the reply-deadline days to the plan's timing, and keep it a
  plain count of days.
- Sign off as the user. Add no typed prices, dates with years, or
  account numbers in the literal text.

Template:

```text
Hello,

I am writing about a purchase I made from you. {fact:what-happened}
I would like a refund of {offer} to my original payment method.

{fact:evidence-summary} I am happy to send any other records you need.

Could you please review this and process the refund? If I have not
heard back within 14 days, I will follow up here.

Thank you for your time.
```
