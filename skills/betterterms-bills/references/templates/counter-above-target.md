# Counter above target

Reply when their counter sits above the plan target. Quote their
number back, restate yours, and move one ladder step with a reason.

Draft fields:

- `action`: `send`
- `offer`: the next ladder step
- `period`: `month`
- `claims`: the fact ids the template renders

`{quote:n}` renders the n-th inbound amount as a bare number, so
write the period in words ("a month", "a year") and match how the
counterparty stated it.

```text
Thanks for checking on this. {quote:1} a month is still more than I
can pay for this plan.

{fact:competitor-price}

I could stay at {offer} on my current plan. If that is out of reach,
what can you do on the monthly price with autopay or a longer term?
```
