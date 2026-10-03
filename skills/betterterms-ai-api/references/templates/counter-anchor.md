# Template: counter anchored on your number

Use when: the vendor quoted a price above target and you want to
counter with one figure and a reason.

```text
Hello,

Thank you for the quote. {quote:1} is above where we can land this
term, given our budget and usage forecast.

We are ready to move ahead at {offer} on an annual term. If that
price is tight on your side, we can discuss a longer term or a ramp
that grows with our usage.

Best,
```

Notes:

- `{quote:1}` renders the first amount from the inbound `amounts`
  list; drop or adjust the sentence when quoting nothing back.
- `{offer}` renders the draft offer with its period. Set the draft
  `offer` to the anchor from `plan.yaml`, and `period` to match.
- Swap the alternative line for a real plan option when one exists;
  the reason must be true for this case.
