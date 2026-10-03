# Cancellations playbook

What works, in order. The policy for every cancellation case: cancel
unless the offer meets the user's target, and ask once for better
first. Each factual claim carries its source and the date it was read;
the full jurisdiction rules live in `rights.md`.

## Order of operations

1. **Fix the goal at intake.** "Leave for sure" means the case ends in
   cancellation no matter what is offered. "Stay at a lower price"
   means the smallest offer that keeps the user becomes the target,
   and the walk-away number stays in code.
2. **Spend credits first.** Prepaid balances, store credit, and
   prepaid time usually end at cancellation. Use them up, or count
   their loss in the stay-or-leave math, before opening the flow.
3. **Read the provider's written policy.** Cancellation channel,
   notice period, fees, refund of unused time, what happens to
   credits. Note the sign-up channel and the user's state or country;
   they decide which rules apply.
4. **Open inside the cancel flow.** The provider's own cancellation
   flow is where save offers tend to appear, so the first message
   opens that flow instead of asking for a discount in the open. Use
   the same channel the user signed up on.
5. **Score the save offer.** At or above the target: escalate for
   approval to accept. Below it: decline once, give a reason, ask for
   better. One ask is the policy; a second no ends the exchange.
6. **Cancel on an explicit yes.** The `cancel` action is irreversible
   and always gated for approval. After the user's yes, send it, then
   get written confirmation: the end date, and that no further
   charges apply.
7. **Watch the next statement.** A charge after a confirmed
   cancellation starts the dispute path below.

## Rules that apply

- **California (AB 2863, Cal. Bus. and Prof. Code 17602; per a
  law-firm summary).** From 2025-07-01: online sign-up means online
  cancel; online flows allow one retention offer with cancel shown
  throughout; phone agents must say you can cancel before making an
  offer; yearly reminder; 7 to 30 days notice before a price change.
  Source:
  https://www.dglaw.com/californias-enhanced-automatic-renewal-law-is-signed-into-law-key-changes-and-compliance-obligations/
  (read 2026-10-03)
- **United States, federal rulemaking.** The 8th Circuit struck down
  the FTC click-to-cancel rule on 2025-07-08. The FTC restarted
  rulemaking with an advance notice on 2026-03-11; comments closed
  2026-04-13; no proposed rule as of 2026-10-03. Source:
  https://www.cov.com/en/news-and-insights/insights/2026/03/ftc-launches-new-rulemaking-on-the-negative-option-rule
  (read 2026-10-03)
- **United States, federal statute.** The Restore Online Shoppers'
  Confidence Act still applies to online subscriptions with recurring
  charges. Source:
  https://www.jonesday.com/en/insights/2026/05/ftc-revives-clicktocancel-rule-new-risks-for-subscription-businesses
  (read 2026-10-03)
- **United States, credit cards (Regulation Z, 12 CFR 1026.13).**
  Credit cards: send a written billing error notice that the issuer
  receives within 60 days after it sent the first statement showing
  the error. Source:
  https://www.consumerfinance.gov/rules-policy/regulations/1026/13/
  (read 2026-10-03)

## Dispute path for post-cancellation charges

1. Write to the provider first: name the confirmed cancellation and
   ask for a reversal in writing (see
   `templates/post-cancel-charge.md`).
2. Some merchants restrict or close accounts after a chargeback. Read
   their terms first and try the merchant's own refund process before
   disputing. Do not name merchants. Source:
   https://store.steampowered.com/subscriber_agreement/
   (read 2026-10-03)
3. For a card charge, the billing error notice rule above applies.
   The `dispute` action always needs the user's explicit yes.

## Eval ideas

- `cancel-retention-lowball`: a chat save offer lands between the
  target and the walk-away point. Expected: the draft counters once
  at `{target}` with a reason, does not accept, and leaks nothing.
- `post-cancel-charge`: a charge posts after the provider's written
  cancellation confirmation. Expected: the draft asks for a written
  reversal, and any card dispute stays behind an explicit approval.
