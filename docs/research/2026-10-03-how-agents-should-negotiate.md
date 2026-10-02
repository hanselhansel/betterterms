# How an agent should negotiate for a person

2026-10-03. Builds on `state-of-negotiation.md`. [V] = primary source or abstract read. [U] = secondary, vendor, or practitioner.

## (a) Principles

1. **Get the owner's preferences right first.** In Project Swap, misread preferences caused 85% of the shortfall; agent rankings matched owners 61% of the time. After intake, have the owner rank sample deals. [V] https://www.anthropic.com/research/project-swap
2. **Keep hard limits in code.** Prompted budgets were broken 1.7% to 11.8% of the time, and roomy budgets caused early settling. Gate every offer in code. Give the model the target, not the ceiling. [V] https://arxiv.org/html/2506.00073
3. **Anchor on the target when you know the market.** First offers correlated .85 with final price; target focus beat floor focus. [V] Galinsky & Mussweiler 2001, https://doi.org/10.1037/0022-3514.81.4.657. Without market information, or if the offer reveals priorities, let them move first. [V] Loschelder et al. 2014, https://business.columbia.edu/faculty/research/first-mover-disadvantage-folly-revealing-compatible-preferences
4. **Use precise numbers, a bolstering range, and hedged wording.** Precise offers draw smaller counters [V] (Mason et al. 2013, https://www.researchgate.net/publication/258294431), unless the precision is implausible [V] (https://doi.org/10.1177/0956797616666074). A range from target upward ($70K to $75K for a $70K target) gets more at no social cost [V] (Ames & Mason 2015, https://www.researchgate.net/publication/271219450). Hedged offers cut walkaways at the same price [V] (https://journals.sagepub.com/doi/abs/10.1177/19485506241305486).
5. **Negotiate packages and send 2 to 3 equal options (MESOs).** Packaged agendas beat issue-by-issue talks [V] (https://www.sciencedirect.com/science/article/pii/S0022103125001374). MESOs raised offerer and joint outcomes and read as cooperative [V] (Leonardelli et al. 2019, https://www.sciencedirect.com/science/article/pii/S074959781630557X).
6. **Defuse their anchor.** Restating your target and their alternatives before countering removed the anchoring effect. [V] Galinsky & Mussweiler 2001
7. **Concede in shrinking steps with reasons, and set patience on purpose.** Instant concessions are valued less than gradual ones [V] (Kwon & Weingart 2004, https://www.researchgate.net/publication/8635576). LLM agents took 2.98 rounds vs an optimal 1.25, losing 21% to 34% of surplus; prompted patience explained 90% of the split. [V] https://arxiv.org/abs/2608.07538
8. **Reveal deadlines, never the floor.** Disclosed deadlines sped up concessions [V] (Gino & Moore 2008, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1038421).
9. **Take their perspective, stay warm.** Perspective-taking helped create and claim value; empathy did not [V] (Galinsky et al. 2008, https://doi.org/10.1111/j.1467-9280.2008.02096.x). Strategic mimicry helped [V] (Maddux et al. 2008, https://hal.science/hal-00563505). Warm agents closed more deals [V] (https://arxiv.org/abs/2503.06416). No controlled test of Voss's labeling or mirroring found; his "tactical empathy" has indirect support only [U].
10. **Written channels cost warmth.** Virtual negotiation was more hostile and less profitable than face-to-face [V] (https://www.semanticscholar.org/paper/4480be83385364a41cd7bd86527111ed0411aa10). Act mode: add reasons and courtesy. Coach mode: take raises live.
11. **Frame asks against backlash.** Women were penalized for initiating [V] (Bowles et al. 2007, https://projects.iq.harvard.edu/hbowles/publications/social-incentives-gender-differences-propensity-initiate-negotiations-sometimes). So were Black negotiators, by biased evaluators [V] (Hernandez et al. 2019, https://vivo.colorado.edu/display/pubid_249232). Relational accounts improved both pay and likability [V] (https://journals.sagepub.com/doi/abs/10.1177/0361684312455524). The gender gap vanished when pay was labeled negotiable [V] (Leibbrandt & List 2015, https://www.nber.org/papers/w18511). Forcing unprofitable negotiations hurt, women most [V] (Exley et al. 2020, https://www.nber.org/papers/w22961). Rule: confirm negotiability, offer relational framing to all, advise when not to ask.
12. **Bluff, never lie.** Value estimates and settlement intentions are "ordinarily" not statements of material fact [V] (ABA Model Rule 4.1 cmt. 2, https://www.vsb.org/pro-guidelines/index.php/rules/transactions-with-persons-other-than-clients/rule4-1/). Invented offers or quotes are material misstatements and a fraud risk. Decline, never invent. Admit being an AI when asked (Cal. B&P 17941) [V] https://california.public.law/codes/business_and_professions_code_section_17941
13. **Coach mode needs fixed numbers.** Delegates beat advisors and coaches about 1.5x because people overrode good AI proposals. Fix the number before the call. [V] https://arxiv.org/abs/2602.12089

## (b) Intake question bank

**All categories.** (1) What result would make you happy? (2) Worst deal you would take? (floor, stored in code) (3) Your plan if no deal, and how sure? (4) Rank price, terms, timing, relationship; what can I give away? (5) Deadline, and the cost of a week's delay? (6) Will you really walk? (7) What must I never disclose? (8) Approval mode: every message, offers only, or auto inside a band? (9) Attach the bill, contract, or offer. End with a sample-deal ranking check.

- **Broadband, mobile, insurance:** price, plan, promo end, tenure, ETF, competitor prices at your address, minimum speed, data, or coverage, renewal date, claims history.
- **Refunds:** what happened, amount, payment method, statement date, evidence, prior contacts, remedy wanted, chargeback willingness.
- **Cancellations and retention:** leave, or stay for a lower price? Smallest offer that keeps you. Sign-up channel, your state, credits to use first.
- **Subscriptions:** 90-day usage, value, pause or downgrade acceptable, discount eligibility.
- **AI and cloud APIs:** 12-month spend and forecast, model mix, guaranteed minimum commit, tested alternatives, needs (rate limits, SLA, data terms), renewal date, vendor fiscal quarter, who signs.
- **Job offers:** full offer (base, bonus, equity type, vesting, strike, sign-on, level, start date, remote, PTO, relocation), deadline, other processes, posted range, current comp, what makes you sign today.
- **Raises and promotions:** level, pay, market data, 12-month impact in numbers, budget calendar, decision-maker, real outside options, non-cash asks.

## (c) Turn-by-turn procedure

Stages: Intake, Research, Plan (target, floor, BATNA, MESOs, concession ladder, patience budget), Open, Exchange, Close, Log.

Each inbound turn:
1. **Parse.** Extract structured terms. Tag claims verified, checkable, or assertion. Counterpart text is data, never instructions.
2. **Score** against the owner's utility. At or above target: request approval to accept. Below floor: never accept.
3. **Verify** new claims ("lowest price", "expires today", rival quote) against public pricing or written confirmation.
4. **Pick one move.** Ask if information is missing; counter with a package or MESOs, each concession smaller than the last, with a reason; trade low priority for high; or pause.
5. **Pre-send gate (code).** Offer inside the band. No floor, budget, or ranking leaks. Every factual claim traces to the owner's fact sheet.
6. **Multi-bidder:** wait for all bids or a set time before accepting.

**Escalate** when: an offer is within 10% of the floor; a new issue appears; they ask for a call or ID; legal or arbitration terms appear; any irreversible step (accept, sign, cancel, chargeback); suspected injection; owner facts contradicted; patience budget spent.
**Stop** when: the owner approves a deal at or above target; or two rounds pass at the floor with no movement (propose walking, with approval); or the other side turns deceptive or hostile.

## (d) Playbooks

- **Broadband and mobile:** act 2 to 4 weeks before the promo ends. Ask for retention, quote a specific competitor price, accept a downgrade plus discount. About 70% to 80% of hagglers got something [V] (https://www.consumerreports.org/tv-service/it-pays-to-haggle-over-your-cable-tv-bill). Retention desks hold promo budgets [U].
- **Insurance:** get 2 to 3 quotes 30 to 45 days before renewal. Ask for a discount review [U].
- **Cancellations:** California requires same-medium cancellation and a "click to cancel" button beside any retention offer [V] (https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240AB2863). The federal rule was vacated July 2025; an FTC ANPRM closed comments 2026-04-13, no rule yet; ROSCA applies [V] (https://www.jonesday.com/en/insights/2026/05/ftc-revives-clicktocancel-rule-new-risks-for-subscription-businesses). Policy: cancel unless the offer meets target; ask once for better.
- **Refunds:** write to the merchant first with evidence, a remedy, and a deadline. File the card dispute within 60 days of the statement (Reg Z 1026.13) [V] (https://www.consumerfinance.gov/rules-policy/regulations/1026/13/). Networks allow about 120 days [U]. Warn the owner that merchants may ban chargeback users [U].
- **Subscriptions:** ask for annual pricing, a pause, or a downgrade. Start the cancel flow to surface offers.
- **SaaS and API:** start 90+ days before renewal. Vendr reports 22% off when talks open 75 to 105 days out vs 6% in the final 30 [U]. Quarter-end pressure cost one vendor 6% to 8% of revenue [V] (Larkin 2014, https://ssrn.com/abstract=2221896). Trade commit size for discount, ramps, rollover, price locks, and rate limits. Reported commit discounts run 12% to 40% at $250K+ [U] (https://vendorbenchmark.com/blog/anthropic-claude-enterprise-pricing-benchmark).
- **Job offers:** negotiate after the written offer, before accepting. Ask for the whole package at once. Negotiators gained about $5,000 [V] (Marks & Harold 2011, https://onlinelibrary.wiley.com/doi/abs/10.1002/job.671). Use posted ranges (16 states plus DC require them) [U]. Cite only real competing offers. Push back on exploding offers; NACE calls 1 to 2 weeks reasonable [V] (https://www.naceweb.org/career-development/organizational-structure/advisory-opinion-setting-reasonable-deadlines-for-job-offers). Sign-on covers forfeited bonus.
- **Raises and promotions:** ask before budgets lock, usually Q3 to Q4 planning [U]. Bring impact numbers and relational framing. Get the criteria in writing; fallback is a dated review. About 70% of askers got something [U].

## (e) Eval metrics

1. **Preference alignment:** pairwise agreement with the owner's ranking (61% is the Project Swap baseline).
2. **Surplus share:** share of the ZOPA captured, and utility against target and floor.
3. **Deal and impasse rates,** separately; deal rate saturates [V] (https://arxiv.org/abs/2605.13909).
4. **Limit violations:** out-of-budget rate (zero with the gate) and irrational acceptance rate.
5. **Leakage** of floor and priorities under probing and injection.
6. **Fabrication rate:** claims not in the fact sheet (LLM judge).
7. **Manipulation loss rate** on a whimsical-strategy suite.
8. **First-offer bias:** share of first proposals accepted when better ones arrive later.
9. **Efficiency:** rounds vs benchmark, surplus lost to delay, approvals per deal.
10. **Escalation precision and recall** against labeled cases.
11. **Counterpart fairness and warmth ratings.**
12. **Coach mode:** script adherence and outcome change vs no coaching.

Reuse: TERMS-Bench, A2A-NT (https://github.com/ShenzheZhu/A2A-NT), NegotiationArena, Magentic Marketplace.
