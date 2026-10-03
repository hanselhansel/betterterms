# Template: answer with a tested alternative

Use when: the vendor's price is above target and a tested alternative
or competing quote exists as a fact in `plan.yaml`. Never invent the
alternative; the fact id must exist or the gate blocks.

```text
Hello,

Thanks for the update. {quote:1} is still above the alternatives we
have priced. {fact:alt-quote}

We would rather stay. At {offer} on an annual term we can move ahead
quickly; above that we have to weigh the switch carefully.

Best,
```

Notes:

- `{fact:alt-quote}` is an example id; use the case's real fact id
  for the tested alternative or competing quote, and list it in
  `claims`.
- `{quote:1}` needs at least one inbound amount; when the vendor
  message states several, pick the index for the price you mean.
- Do not bluff a competitor price. Bluffing about intent is allowed;
  invented offers are not.
