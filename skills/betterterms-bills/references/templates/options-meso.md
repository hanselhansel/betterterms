# Offer equal options

Send 2 or 3 options worth the same to the user, so the counterparty
picks a shape instead of fighting one number.

Draft fields:

- `action`: `send`
- `offer`: null
- `period`: `month`
- `claims`: empty or the fact ids the template renders

Labels inside `{option:...}` must match `plan.yaml` option labels
exactly. List only the options the plan holds.

```text
I want to make this work, and I see a few ways to get there:

- {option:keep-plan}: keep my current plan.
- {option:downgrade}: move to a lower tier on the same network.
- {option:annual}: prepay the year for a lower monthly rate.

Each of these fits what I need. Which can you do?
```
