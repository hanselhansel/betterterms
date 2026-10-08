# Open: ask retention for a better price

First message to a broadband, cable, or mobile provider when a promo
price is ending or the bill went up.

Draft fields:

- `action`: `send`
- `offer`: the plan target or ladder step 1
- `period`: `month`
- `claims`: the fact ids the template renders

Replace the example fact id with a real one from `plan.yaml`. Keep
the tenure line only when intake confirms real tenure; drop it
otherwise.

```text
Hi, my promotional price ends soon and the new monthly price is more
than I want to spend. I have been with you a while and I would like
to stay, but the bill needs to come down.

{fact:competitor-price}

Could you bring my monthly price closer to {offer}? I am happy to
keep my current plan if we can get there. Thanks for looking into it.
```
