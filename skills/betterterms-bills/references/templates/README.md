# Message templates

Voice-neutral drafts for the bills pack, warm with reasons and
courtesy because written channels lose warmth. Each file holds one
`template` value for a `draft.yaml`, plus the draft fields that go
with it.

## Placeholder contract

Money enters a message only through placeholders the gate renders:

- `{offer}`: the draft offer, rendered with its period ("$75/month").
- `{target}`: the plan target, rendered with the plan period.
- `{option:<label>}`: a plan option by its `plan.yaml` label.
- `{ladder:<n>}`: the n-th ladder entry.
- `{fact:<id>}`: a plan fact's text, verbatim; also claims the id.
- `{quote:<n>}`: the n-th amount in the inbound `amounts` list,
  rendered bare; write the period in words yourself.

Never type a price, a currency word, or a number into the literal
text. Fact ids and option labels in these files are examples; swap in
the real ids and labels from the case's `plan.yaml` before gating.

Words that read like accepting ("deal", "I accept", "works for me")
force an approval even in a plain `send`. These templates avoid them;
keep it that way when editing.
