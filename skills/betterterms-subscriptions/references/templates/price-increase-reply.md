# Price-increase reply

When to use: answering a renewal or price-change notice before the new
price starts. `{quote:1}` refers to the first amount in the inbound
`amounts` list, so use this only on a turn that answers their notice.
Replace `<service>` with the product name. Every placeholder must
resolve or the gate blocks the draft.

```text
Hello, I saw the notice that my <service> price is changing to
{quote:1}. I have been a customer for a while and the new price does
not fit my budget. Before it takes effect, could you keep my current
rate, or offer something closer to {target}? I would much rather stay
than start looking at alternatives. Thank you.
```
