# Discount eligibility check

When to use: the user qualifies for a discount class (student,
education, nonprofit, annual) that was not offered. Use `{fact:f1}`
only when the plan holds a fact confirming the discount exists; replace
`<discount class>` with the real class. Every placeholder must resolve
or the gate blocks the draft.

```text
Hello, a quick question about my <service> subscription. I believe I
qualify for your <discount class> pricing, and {fact:f1} Could you
apply it to my account, or tell me which plan it applies to? If it gets
me near {target} I am happy to stay. Thank you for your help.
```
