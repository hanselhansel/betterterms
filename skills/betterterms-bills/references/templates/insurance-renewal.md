# Insurance renewal: ask for a discount review

Use before the renewal date, with competitor quotes for the same
coverage in hand.

Draft fields:

- `action`: `send`
- `offer`: the target premium, or null when the ask is a review
- `period`: `year` for an annual premium, `month` for a monthly one
- `claims`: the fact ids the template renders

Replace the example fact ids with the quote facts in `plan.yaml`.
Keep the record line only when intake confirms a clean recent record;
drop it otherwise.

```text
My renewal notice shows a higher premium for the same coverage. I
have been with you a while and my recent record is clean.

I hold written quotes for the same coverage:

{fact:quote-1}
{fact:quote-2}

Could you review my policy for discounts, or match one of these? I
would rather stay than switch. Thank you.
```
