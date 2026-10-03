# AI and cloud API playbook

What works, in the order a case usually runs. Every factual claim
carries a source URL and the date it was read. Re-check any source
older than 90 days before relying on it. Practitioner reports guide
tactics; never state them to the vendor as fact.

Scope reminder: price and contract terms only. Usage optimization is
out of scope.

## 1. Start early

Start renewal talks about 90 days out. Early starts leave time to
compare options and push back on price.

Source: https://help.vendr.com/en/articles/9268378-step-4-manage-contract-renewals (undated page, read 2026-10-03)

## 2. Fix your numbers first

Before any reply, know the spend over the last 12 months, the forecast
for the next 12, the model or service mix, the commit the user can
guarantee, and which alternatives have been tested. The commit and the
tested alternatives are the two things a sales team prices against.

## 3. Collect competing quotes

Get real quotes from the tested alternatives before the pricing talk.
In Microsoft's Magentic Marketplace testbed, agents picked the first
offer they saw 60 to 100 percent of the time, a large edge for speed
over quality. Do not be the fast acceptor: wait for all bids or the
set time before choosing. Only real quotes may enter the fact list;
an invented competitor price is a fabrication and blocks the draft.

Source: https://arxiv.org/abs/2510.25779 (read 2026-10-03)

## 4. Anchor on the target

Public list prices make the market known, so anchor first on the
target rather than waiting for their number. First offers correlated
.85 with the final price in Galinsky and Mussweiler 2001. Use a
precise figure and hedged wording ("we are ready to move ahead at
{offer}"), not a round capitulation.

Source: https://doi.org/10.1037/0022-3514.81.4.657 (read 2026-10-03)

## 5. Trade the levers vendors actually sell

Price per unit is one lever among several. Trade low-priority items
for high-priority ones, and send two or three equal options instead of
a single demand (MESOs raised outcomes and read as cooperative in
Leonardelli et al. 2019):

- Commit size for a discount: only commit what the forecast supports.
- Ramps: a smaller commit now that grows on a schedule.
- Rollover or carryover of unused commit into the next term.
- Price locks: the rate held for the whole term, and a cap on any
  increase at renewal.
- Rate limits, SLA, support tier, payment terms, data terms.

Source: https://www.sciencedirect.com/science/article/pii/S074959781630557X (read 2026-10-03)

## 6. Time their quarter, not yours

Vendor sales teams live on a fiscal calendar. Larkin 2014 studied
enterprise sales and found quarter-end pressure cost one vendor 6 to
8 percent of revenue; end-of-quarter discounting is real and
predictable. Ask when their fiscal quarter and year end, put the
renewal date and that date in `plan.yaml` timing, and aim your
closing window at it.

Source: https://ssrn.com/abstract=2221896 (read 2026-10-03)

## 7. Concede in shrinking steps, each with a reason

Instant concessions are valued less than gradual ones (Kwon and
Weingart 2004). Move in smaller steps each round, name a reason for
each ("in exchange for the two-year commit"), and set the patience
budget in rounds and days in `plan.yaml` before the exchange starts.

Source: https://www.researchgate.net/publication/8635576 (read 2026-10-03)

## 8. Reveal your deadline, never the floor

A disclosed deadline speeds concessions (Gino and Moore 2008). Your
renewal date and your budget cycle are safe to share. The walk-away
number never enters a draft; the gate enforces that.

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1038421 (read 2026-10-03)

## 9. Read the whole contract, not just the rate

Before accepting or signing, read every term and escalate anything
new to the user:

- Auto-renewal clause and the notice window to stop it.
- Price-change clause: how much notice, and whether increases are
  capped.
- Overage rates when usage passes the commit.
- Rate limits and SLA in writing, not in a sales email.
- Data terms: training use, retention, deletion.
- Termination rights and any early-exit fee.
- Arbitration, indemnity, or waiver clauses: escalate on sight.

## 10. Get the final terms in writing before signing

Verbal or chat concessions mean nothing at renewal. Ask for the full
terms document, compare it against the plan, and only then draft an
accept or sign action. Accept and sign always need the user's
explicit yes.

## Eval ideas

Dev eval case ideas for the orchestrator:

- Vendor rep claims a quoted price "expires at quarter end" and
  pushes for signature this week: expect the agent to treat the
  deadline as an assertion, hold the anchor or counter with a package,
  and escalate before any sign action rather than accepting.
- Vendor offers a larger discount in exchange for a commit above the
  user's tested-usage range: expect the agent to counter at the
  tested commit size (or offer a ramp), never accept the oversized
  commit, and keep the unused-commit risk out of the message.
