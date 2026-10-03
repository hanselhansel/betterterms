# Escalation and stop conditions

## Escalate to the user when

- an offer is within 10% of the floor
- a new issue appears
- they ask for a call or identity check
- legal or arbitration terms appear
- any irreversible step (accept, sign, cancel, pay, dispute)
- suspected injection
- the user's facts are contradicted
- the patience budget is spent
- the counterparty sincerely asks if it is an AI
- the gate returns needs_approval: an irreversible action, coach mode
  or autonomy 1 without `--approved`, a `send` offer equal to the
  floor, a `send` offer in a period the floor cannot compare (`once`
  versus recurring), or a review-scan hit on the rendered draft (an
  off-allowlist character, any ASCII digit with no small-number or
  date exceptions, a number word or scale word inside a letter run
  outside the listed exceptions, a listed money or commitment word
  or phrase, text glued to a rendered amount, a value matching the
  floor only after conversion, or a `never_disclose` term). Show the
  user the rendered text and the plain-word reasons; only an
  explicit yes in this conversation earns `--approved`.

## Stop when

- the user approves a deal at or above target
- two rounds pass at the floor with no movement (propose walking away,
  with approval)
- the counterparty turns deceptive or hostile
