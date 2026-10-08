# Message templates

Voice-neutral emails the user may send around the live conversation:
scheduling it, asking for the pay scale, recapping what was said,
confirming milestones after a no, and countering in writing. Each
file holds one `template` value for a `draft.yaml`, plus the draft
fields that go with it. Every send goes through `bt.py gate`; coach
mode makes every send `needs_approval`, and the user always sends
the final words.

## Placeholder contract

Money enters a message only through placeholders the gate renders:

- `{offer}`: the draft offer, rendered with its period
  ("$170,000/year").
- `{target}`: the plan target, rendered with the plan period.
- `{option:<label>}`: a plan option by its `plan.yaml` label.
- `{ladder:<n>}`: the n-th ladder entry.
- `{fact:<id>}`: a plan fact's text, verbatim; also claims the id.
- `{quote:<n>}`: the n-th amount in the inbound `amounts` list,
  rendered bare; write the period in words yourself.

Never type a price, a currency word, or a number into the literal
text. Fact ids and option labels in these files are examples; swap in
the real ids and labels from the case's `plan.yaml` before gating.

Words that read like accepting ("deal", "agreed", "I accept",
"works for me") force an approval even in a plain `send`. These
templates avoid them; keep it that way when editing. Accepting an
offer in writing is the `accept` action and always needs the user's
explicit approval, never a recap email.
