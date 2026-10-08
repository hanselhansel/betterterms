# Template: ask for more time to decide

Use when: the offer carries a short deadline and the user needs a
real window to decide. Cite the decision-window fact from
`plan.yaml`.

Draft fields:

- `action`: `send`
- `offer`: null
- `claims`: the fact ids the template renders

```text
Subject: Re: offer timeline

Hi <name>,

Thank you for the offer. I am excited about the role and want to
give this the thought it deserves.

{fact:decision-window}. Could I have until <date> to give you a
final answer? I will reply by then for sure.

Best,
```

Notes:

- `{fact:decision-window}` is an example id; use the real plan fact
  citing the source on reasonable offer windows.
- Asking for time discloses a deadline the user controls. It never
  discloses limits.
