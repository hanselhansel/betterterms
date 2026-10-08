# Opening retention ask

When to use: the first message to a vendor the user wants to keep at a
lower price. Replace `<service>` and the reason with case details. Use a
`{fact:<id>}` line only when `plan.yaml` has a matching fact id; drop the
placeholder otherwise. Every placeholder must resolve or the gate blocks
the draft.

```text
Hello, I have been a <service> subscriber for a while and I would like
to stay, but the current price no longer works for me. {fact:f1} Is
there a loyalty or retention rate closer to {target}? I am open to a
different tier or billing period if that makes it easier. Thank you for
your time.
```
