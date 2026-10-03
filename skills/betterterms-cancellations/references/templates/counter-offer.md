# Counter a save offer

Use when the retention offer does not meet the target. Action:
`send`. `n` in `{quote:n}` indexes the inbound `amounts` list, so it
names their offer back to them. Replace `id` in `{fact:id}` with a
fact from `plan.yaml` (a competitor price, a usage fact, a stated
reason); drop the placeholder when no fact applies. When the plan
holds a downgrade option, naming it with `{option:<label>}` gives the
agent a concrete alternative to close on.

```
Thank you for the offer of {quote:1}. I would like to stay, but the
price has to fit my budget. {fact:id} I could keep the service at
{target}. Can you do that?

If not, I will go ahead and finish the cancellation.
```
