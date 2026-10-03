# Template: recap after the call

Use when: the user just had the call and needs a written recap that
locks in what was said without agreeing to anything. The amounts the
recruiter stated enter through `{quote:n}`.

Draft fields:

- `action`: `send`
- `offer`: null
- `claims`: empty or the fact ids the template renders

```text
Subject: Recap of our call today

Hi <name>,

Thank you for the time today. Confirming what I heard: an offer of
{quote:1} on the terms we discussed, and you asked for my answer by
<date>.

I am excited about the role and reviewing the package carefully. I
will reply by <date> as promised. Please correct me if I got any of
that wrong.

Best,
```

Notes:

- `{quote:1}` renders the first amount from the inbound `amounts`
  list extracted from the user's recap. Point the index at the
  package figure, not at a date or a term length.
- A written recap creates a record. Keep the wording warm and
  neutral; it agrees to nothing.
