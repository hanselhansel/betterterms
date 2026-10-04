# Pay scale request

Ask HR or the manager for the pay scale of the user's position, or
of the target level, in writing. Some states and countries grant this by
rule (see `../rights.md`); elsewhere it is a normal request under
the company's own pay-band policy. Either way it grounds the market
data in `plan.yaml` facts.

Draft fields:

- `action`: `send`
- `offer`: null
- `period`: `once`
- `claims`: the fact ids used (for example a policy or rights fact)

```text
Hi <name>,

As I prepare for our review conversation, could you share the pay
scale or band for <current level> and for <target level>? {fact:f-band}
would point me to it, but I would rather get the current figure
from you directly.

Thank you,
```

Notes:

- `{fact:f-band}` renders a plan fact, for example the company's
  written band policy or the local rule the user cites.
  Swap in the case's real fact id; drop the sentence if the plan
  holds no such fact.
- Never quote a band the company has not stated. If only public
  ranges exist, say so plainly instead of implying an internal
  figure.
