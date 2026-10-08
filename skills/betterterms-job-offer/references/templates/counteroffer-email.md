# Template: the ask in writing

Use when: the recruiter asks for the ask in writing, or the user
prefers email over the call. `{offer}` renders the counter with its
period; `{fact:<id>}` carries the reasons.

Draft fields:

- `action`: `send`
- `offer`: the ask from the plan ladder
- `period`: `year`
- `claims`: the fact ids the template renders

```text
Subject: Re: offer for <role>

Hi <name>,

Thank you again for the offer. I am excited about <the role or the
team> and want to make this work.

{fact:range}. With that in mind, I am looking for a base of {offer}.

If base is capped, I could get there through sign-on or equity
instead. Happy to talk through whichever fits best.

Could you send the updated offer in writing once we land somewhere?

Best,
```

Notes:

- `{fact:range}` is an example id; use the real plan fact (posted
  range or market data) and add its id to `claims`.
- Set `offer` to the rung of the ladder this turn sits on, with
  `period` matching the plan period. Never state the walk-away
  number.
