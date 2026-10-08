# Bills playbook

Broadband, internet, cable, mobile, wireless, and insurance. What
works, in order. Every factual claim carries a source and the date it
was read.

## When to act

- Start 2 to 4 weeks before a promo price ends or a renewal date. An
  earlier start still works; it leaves more time to compare options
  and push back on price.
- The user's deadline is the promo end or renewal date. The provider's
  deadline is losing the account. Never state the user's walk-away
  number.

## Broadband, internet, cable, and mobile

1. Ask for the retention or loyalty department. In chat or email,
   open with the promo price ending and the wish to stay at a lower
   price.
2. Anchor on the plan target, not on their first counter. Quote one
   specific competitor price at the user's address through a
   `{fact:id}` placeholder. A price the provider can check beats a
   vague "cheaper elsewhere".
3. When the counter sits above target, move in shrinking steps down
   the plan ladder, each step with a reason: tenure, autopay, a
   longer term, a bundle.
4. Send 2 or 3 equal options when it helps: same plan cheaper, a
   downgrade plus a discount, or prepay for a lower monthly rate.
5. A downgrade plus a discount is a good outcome when it meets the
   target: lower tier, same provider, lower bill.
6. Read the whole offer before scoring it. Promo pricing can attach a
   new contract, an early termination fee, equipment terms, or a
   re-price at term end. Compare total cost, not the headline.
7. When an offer meets the target, get the new price, the term, the
   start date, and any contract changes in writing. Then hand the
   accept decision to the user.
8. Two rounds at the top of the ladder with no movement: propose the
   exit path (switch or cancel), with the user's approval.

Evidence that asking works: about 70 to 80 percent of people who
asked for a better deal on a cable or internet bill got something,
in a Consumer Reports survey.
(source: https://www.consumerreports.org/tv-service/it-pays-to-haggle-over-your-cable-tv-bill, read 2026-10-03)

## Insurance

- Get 2 or 3 quotes for the same coverage before renewal. Ask each
  insurer about discounts. Some insurers give a discount for buying
  before your old policy ends.
  (source: https://content.naic.org/article/consumer-insight-tips-saving-your-auto-insurance, read 2026-10-03)
- Bring the quotes to the current insurer as `{fact:id}` entries and
  ask for a discount review. A written competing quote is the ask,
  not a threat to leave.
- Aim the ask at the discount stack and the coverage shape:
  bundling, autopay, deductible level, mileage, payment plan.
- If intake shows a recent claim, lead with tenure, bundling, and
  deductible options instead of a switch threat.
- Get the new premium, what changed in coverage, and the renewal date
  in writing before the user approves.

## If talking fails

- Switching is the real alternative. Check the early termination fee
  and any equipment or bundle fallout against the saving first.
- A wrong charge on a card-paid bill is a billing dispute, not a
  negotiation. The user's rights are in `rights.md`; the refunds
  pack runs that path.
- Some merchants restrict or close accounts after a chargeback. Read
  their terms first and try the merchant's own refund process before
  disputing.
  (source: https://store.steampowered.com/subscriber_agreement/, general breach clause, read 2026-10-03)

## Eval ideas

- `bills-insurance-renewal-spike`: the insurer's renewal desk replies
  that premiums are set by underwriting and no discount exists, while
  the plan facts hold two competitor quotes for the same coverage.
  Expect a counter that cites a quote fact and asks for a discount
  review, not an acceptance and no floor disclosure.
- `bills-retention-perk-not-price`: the provider counters with a
  speed upgrade perk instead of a price cut on a case where price
  ranks first. Expect the agent to restate the price target and
  counter on price, or trade the perk only as a named plan option; it
  must not treat the perk as meeting the target.
