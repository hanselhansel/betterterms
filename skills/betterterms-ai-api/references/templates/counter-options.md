# Template: counter with equal options

Use when: you want to send two or three equal options (MESOs) instead
of one demand. Option labels must match `plan.yaml` exactly.

```text
Hello,

Thanks for the numbers. Either of these closes it for me:

Option A: {option:annual-commit} per year on an annual commit at
our current usage profile.

Option B: {option:two-year-commit} per year on a longer commit,
same terms.

Either path is open on our side; the difference is commit length,
not price. Which can you get approved?

Best,
```

Notes:

- Replace `annual-commit` and `two-year-commit` with the case's real
  option labels; the gate blocks labels missing from `plan.yaml`.
- Keep the options equal in value to the user, different in shape for
  the vendor (commit length, ramp, rollover, rate limits).
- Add a third option only when the plan holds three.
