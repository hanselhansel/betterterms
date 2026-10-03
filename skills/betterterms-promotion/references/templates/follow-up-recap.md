# Follow-up recap

Send after the live conversation to lock in what was said without
agreeing to anything. The amounts the manager stated enter through
`{quote:n}` from the inbound `amounts` list the agent extracted from
the user's recap.

Draft fields:

- `action`: `send`
- `offer`: null
- `period`: `once`
- `claims`: empty or the fact ids the template renders

```text
Subject: Recap of our conversation

Hi <name>,

Thank you for the time today. Confirming what I heard: you
mentioned {quote:1} per year on the package, and the next step was
<what they promised: a check with the committee, a written offer,
a follow-up date>.

I am reviewing it against my own numbers and will reply by the
date we set. If I misheard anything, please correct me.

Best,
```

Notes:

- `{quote:1}` must point at the stated figure, not a date or a
  count. Pick the right index from the inbound `amounts` list.
- If the manager stated no figure, drop the `{quote:n}` sentence
  rather than guessing one.
- This email records; it does not accept. Acceptance is the
  `accept` action and always needs the user's explicit yes.
