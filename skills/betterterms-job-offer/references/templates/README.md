# Follow-up email templates

Voice-neutral drafts for the job-offer pack, warm with reasons and
courtesy because written channels lose warmth. Each file holds one
`template` value for a `draft.yaml`, plus the draft fields that go
with it. These are follow-up emails around the live conversation:
the user negotiates on the call, these put it in writing.

## Placeholder contract

Money enters a message only through placeholders the gate renders:

- `{offer}`: the draft offer, rendered with its period ("$181,000/year").
- `{target}`: the plan target, rendered with the plan period.
- `{option:<label>}`: a plan option by its `plan.yaml` label.
- `{ladder:<n>}`: the n-th ladder entry.
- `{fact:<id>}`: a plan fact's text, verbatim; also claims the id.
- `{quote:<n>}`: the n-th amount in the inbound `amounts` list,
  rendered bare; write the period in words yourself.

Never type a price, a currency word, or a number into the literal
text. Fact ids and option labels in these files are examples; swap in
the real ids and labels from the case's `plan.yaml` before gating.

Coach mode gates every send to `needs_approval`; the user sends the
final words. Words that read like accepting ("deal", "agreed", "I
accept", "works for me") force an approval even in a plain `send`.
These templates avoid them; keep it that way when editing.
