# Target record

One record per candidate negotiation target, written to `targets.yaml`
in the case folder. The user picks which records go forward to research.

## Fields

| Field | Content |
|---|---|
| `counterparty` | Who the user would negotiate with (vendor, provider, employer) |
| `amount` | Current price or offer as a plain number, in `period` units |
| `period` | `once`, `month`, or `year`: how often `amount` is paid or received |
| `renewal_date` | Next renewal, promo end, or decision deadline as an ISO date, or null |
| `evidence` | Where the record came from: file name, message subject and date, or a note |
| `usage_signal` | Whether the user still uses or needs this, and the signal that showed it |

## Example

```yaml
- counterparty: Nimbus Broadband
  amount: 85
  period: month
  renewal_date: 2026-11-01
  evidence: "email receipt, subject 'Your October bill', 2026-10-01"
  usage_signal: "in use; nightly streaming per router log export"
```

## Rules

- `amount` is a plain number. Currency belongs to the case, not the
  record.
- Write a record even when evidence is thin; mark the gap in `evidence`.
- `period` is required when `amount` is present, so a monthly bill is
  never read as a yearly one.
