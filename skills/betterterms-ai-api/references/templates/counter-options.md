# Template: counter with equal options

Use when: you want to send two or three equal options (MESOs) instead
of one demand. Option labels must match `plan.yaml` exactly.

```text
Hello,

Thanks for the numbers. Two ways we could close this:

Option one: {option:annual-commit} per year on a one-year commit at
our current usage profile.

Option two: {option:two-year-commit} per year on a two-year commit,
same terms.

Either works for us; the difference is commit length, not price.
Which can you get approved?

Best,
```

Notes:

- Replace `annual-commit` and `two-year-commit` with the case's real
  option labels; the gate blocks labels missing from `plan.yaml`.
- Keep the options equal in value to the user, different in shape for
  the vendor (commit length, ramp, rollover, rate limits).
- Add a third option only when the plan holds three.
