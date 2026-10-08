# Query hygiene

A research query is public text: it can end up in search history, logs,
and autocomplete suggestions. Queries describe the counterparty and the
policy, never the user.

## Never in a query

- Names: the user's, a family member's, anyone's
- Email addresses
- Account, customer, or policy numbers
- Street addresses
- Employer name in a salary or promotion case
- Phone numbers
- Exact salary, or an exact bill amount when it can identify the user

## Generalize instead

- The city or state, not the street address
- The job level and market, not the exact salary
- The provider's name and plan tier, not the account number
- "Satellite internet" pricing, not "my bill of 142.37"

## Good queries

- `acme broadband retention offer 2026`
- `acme cancellation policy site:acme.com`
- `reddit acme internet retention deal`
- `california subscription cancellation law`
- `staff software engineer salary range public levels`

## Bad queries

- `jane doe acme bill refund`
- `acct 7788123 retention discount`
- `jdoe@example.com flight refund claim`
- `acme corp salary negotiation base 152000`
- `555-0142 billing dispute`
- `142 mapleton road internet price`

When a detail would sharpen the search, widen it until it no longer
points at the user, then run the wider query.
