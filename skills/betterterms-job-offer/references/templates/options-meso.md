# Template: equal package options

Use when: the user wants to give the counterparty two or three ways
to say yes instead of one number to fight. Option values render
through `{option:<label>}`; the shape is described in words.

Draft fields:

- `action`: `send`
- `offer`: null
- `claims`: empty

```text
Subject: Re: offer for <role>

Hi <name>,

I am excited about the role and want to make the package work. I
see a few ways to get there:

- {option:base-first} base with standard equity.
- {option:sign-on-shift} base plus a sign-on that covers the bonus
  I would forfeit.
- {option:equity-level} base with an equity or level adjustment.

Each of these fits what I need. Which can you do?

Best,
```

Notes:

- Labels inside `{option:...}` must match `plan.yaml` option labels
  exactly. List only the options the plan holds.
- A rendered option is only its value and period; describe the
  package shape in words, without amounts, like the lines above.
