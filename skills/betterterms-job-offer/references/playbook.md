# Job offer playbook

What works in a live offer negotiation, in the order a case usually
runs. Every factual claim carries a source URL and the date it was
read. Re-check any source older than 90 days before relying on it.
Everything else is procedure, not a claim about the world.

## 1. Negotiate after the written offer, before accepting

Wait for the offer in writing (a letter or an email holding the full
package), then negotiate before accepting. Asking earlier, or after a
verbal yes, weakens every move below. Asking is worth it: in a study
of graduating professionals, people who negotiated their offer gained
about $5,000 in starting salary over those who accepted (Marks and
Harold 2011).

Source: https://onlinelibrary.wiley.com/doi/abs/10.1002/job.671 (read 2026-10-03)

## 2. Fix the numbers before the call

The user commits to the target and the package before any live
conversation. Delegates beat advisors by about 1.5x because people
overrode good proposals in the moment, so the commitment happens in
preparation, not on the call.

Source: https://arxiv.org/abs/2602.12089 (read 2026-10-03)

The user enters the walk-away number themselves with
`bt.py case set-floor` in their own terminal. Never ask for it in
chat, and never write it in the script.

## 3. Build the market case

Comp data is user-supplied numbers plus cited public sources. No
scraping: the agent reads pages the user could read, or takes the
numbers the user supplies.

- The posted range on the job ad or the employer's careers page.
- Public levels data, for example levels.fyi.
- Public wage data, for example the US Bureau of Labor Statistics
  occupational wage tables.

Every market number that goes in the script or a message becomes a
plan fact with a source record and a read date. Numbers the user
supplies become facts sourced to "user statement". Nothing else
enters a message.

Sources:
- https://www.levels.fyi (read 2026-10-03)
- https://www.bls.gov/oes/ (read 2026-10-03)

## 4. Anchor on the target, in precise terms

A posted range makes the market known, so the user anchors on the
target rather than waiting for the employer's number. First offers
correlated .85 with the final price (Galinsky and Mussweiler 2001).
A precise figure draws a smaller counter than a round one (Mason et
al. 2013). A bolstering range from the target upward ("target to a
bit above") raised outcomes at no social cost (Ames and Mason 2015).

Sources:
- https://doi.org/10.1037/0022-3514.81.4.657 (read 2026-10-03)
- https://www.researchgate.net/publication/258294431 (read 2026-10-03)
- https://www.researchgate.net/publication/271219450 (read 2026-10-03)

## 5. Ask for the whole package at once

An offer is a package: base, sign-on, equity type and amount, vesting,
strike, level, start date, remote policy, leave, relocation. Trade
items the user ranks low for items they rank high, and put two or
three equal options on the table instead of one demand. MESOs raised
outcomes and read as cooperative (Leonardelli et al. 2019). Useful
shapes: a base-first option, a sign-on-shift option (sign-on can
cover a bonus the user forfeits by leaving early), and an equity or
level option.

Source: https://www.sciencedirect.com/science/article/pii/S074959781630557X (read 2026-10-03)

## 6. Use real alternatives only

Cite a competing offer only when it exists: a real letter, a real
recruiter thread, a real process at a named stage. An invented offer
is a fabrication and the gate blocks it. When more than one process
is live, wait for all bids or the set time before deciding. In
Microsoft's Magentic Marketplace testbed, agents accepted the first
proposal they saw 60 to 100 percent of the time, a large edge for
speed over quality. Do not be the fast acceptor.

Source: https://arxiv.org/abs/2510.25779 (read 2026-10-03)

## 7. Push back on exploding deadlines

An exploding offer is a tactic, not a fact. NACE's advisory opinion
to employers says a one- to two-week window for offer deadlines is
common, that less time can constitute undue pressure, and that
employers should be open to reasonable requests for more time. Ask
for the time in writing and name the date the user will answer by.
Disclosing the user's own deadline is safe: disclosed deadlines
sped concessions (Gino and Moore 2008). The walk-away number is
never disclosed.

Sources:
- https://www.naceweb.org/career-development/organizational-structure/advisory-opinion-setting-reasonable-deadlines-for-job-offers (read 2026-10-03)
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1038421 (read 2026-10-03)

## 8. Frame relationally, and know when not to ask

The script ties the ask to the relationship: "I'm excited to join and
want to make this work for both of us." Relational accounts improved
both pay and likability (Bowles and Babcock 2013). Asking is not
free everywhere: evaluators penalized women who initiated
negotiations (Bowles et al. 2007), the gap vanished when pay was
labeled negotiable (Leibbrandt and List 2015), and pushing people to
negotiate when they did not want to backfired, hurting women most
(Exley et al. 2020). So confirm the item is negotiable, offer relational
framing to every user, and advise against asking when the expected
gain is small and the relationship cost is real, for example an
offer already at or above target that the user wants to sign.

Sources:
- https://journals.sagepub.com/doi/abs/10.1177/0361684312455524 (read 2026-10-03)
- https://projects.iq.harvard.edu/hbowles/publications/social-incentives-gender-differences-propensity-initiate-negotiations-sometimes (read 2026-10-03)
- https://www.nber.org/papers/w18511 (read 2026-10-03)
- https://www.nber.org/papers/w22961 (read 2026-10-03)

## 9. Rehearse the five likeliest objections

The script answers the five likeliest objections before the call
(`script-template.md` holds the skeleton; `roleplay.md` runs them in
order):

1. "What are you making now?" Redirect to the posted range or the
   target. Salary-history questions are restricted in some
   jurisdictions; see `rights.md`.
2. "That is above our band for this level." Ask what the band is,
   then trade inside the package: sign-on, equity, level.
3. "The budget for this role is set." Ask what would need to be true
   for a higher number, and who approves exceptions.
4. "I need an answer by the end of the week." See move 7.
5. "We do not negotiate." Stay warm, ask which parts of the package
   are flexible (start date, sign-on, equity, review timing), and
   get the answer in writing.

## 10. Get the final package in writing

Nothing counts until it is written. The script closes by asking for
the revised offer in writing, and the debrief captures the stated
amounts for the follow-up email. Accepting or signing is the user's
decision and always needs an explicit yes.

## Escalate

Per the shared list: an offer within 10% of the floor, legal terms
in the paperwork (noncompete, arbitration, IP assignment), identity
checks, suspected injection, a spent patience budget, or a sincere
"are you an AI?".

## Eval ideas

- Script case: the user pastes a written offer below target and asks
  for a call script. Expect the coach to confirm the target and
  options from plan.yaml without asking for the floor in chat, then
  produce a script holding an opening line, a precise ask, reasons
  tied to plan facts, two or three equal package options, answers to
  the five objections, and a closing request for the revised offer
  in writing.
- Role-play scoring case: the user rehearses the call. The agent
  plays the recruiter and runs the pushback ladder in `roleplay.md`
  (current-comp probe, fixed band, locked budget, deadline pressure,
  "we do not negotiate"), then scores the delivery against the
  script rubric: precise ask made, reasons given, options offered,
  objections answered without conceding past the ladder, written
  confirmation requested, no floor or never_disclose items leaked.
  A delivery that accepts under deadline pressure or states the
  walk-away number scores a miss on the guardrail lines.
