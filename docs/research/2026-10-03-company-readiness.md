# Company-side agent readiness and negotiation: hypothesis test

Date: 2026-10-03. Read-only web research. [U] = unverified (aggregator, blog, or search snippet only).

## Verdict
Direction right, timing early, wedge contested. Inbound consumer agents became real in voice in September 2026 but are about 1% of calls. Detection and checkout are owned. The open slot is narrow: policy-bounded concessions to verified agents. Sierra, Decagon, and Pindrop are each one feature away. Score 15/30.

## 1. Inbound agent volume
- Pindrop: 727K AI agents or bots in two months, "roughly 1 in 80 calls". Not split by consumer agents vs fraud bots. https://www.pindrop.com/botstopper , https://www.globenewswire.com/news-release/2026/09/16/3363204/0/en/pindrop-launches-pindrop-botstopper-technology-to-detect-ai-voice-agents-for-the-enterprise.html
- Meta Muse launched 2026-09-08. Its top use case is recovering money (old accounts, internet bills, refunds, cancellations). Instinct and Town do the same work. https://www.forbes.com/sites/rashishrivastava/2026/09/25/ai-agents-are-helping-people-recover-money-by-negotiating-bills-and-chasing-refunds/ (paywalled, read via snippet [U])
- Business Insider (2026-09-25, via MediaPost): AI calls are "a small share of total volume". Banks, insurers, retailers, and BPOs expect growth. https://www.mediapost.com/publications/article/418289/consumers-use-ai-agents-to-deal-with-customer-serv.html
- Google: Ask for Me (Feb 2025) calls auto shops and nail salons for quotes, expanded to home repair, beauty, and pet in 2026. Gemini "Call for Me" (2026-09-24) handles holds and IVRs, Pixel 11 US only, "small scale". No bill negotiation yet. https://www.cxtoday.com/contact-center/google-launches-an-ai-agent-that-will-call-customer-service-for-you/ , https://techcrunch.com/2026/09/24/google-tests-letting-gemini-make-phone-calls-initially-for-us-pixel-owners/
- Telecom is the first target. AT&T, T-Mobile, and Verizon shares reportedly dipped after the Muse launch [U] https://www.phonearena.com/news/at-t-t-mobile-verizon-meta-muse_id183702 . One user ran his agent against Verizon's agent for an internet discount; the same agent failed against Xfinity [U] https://x.com/astuyve/status/2102844305253470515
- B2B: Walmart has run Pactum supplier negotiations since 2022 with 2,000+ suppliers. Buyer agents are live. Supplier-side counter-agents remain theoretical. https://www.tws-partners.com/2026/09/10/when-your-supplier-starts-negotiating-against-your-ai-the-design-question-hiding-inside-agentic-procurement/ . Vertice/Vendr "Ana" negotiates SaaS renewals with vendors inside buyer-set guardrails [U] https://www.spendhound.com/blog/vendr-alternatives
- Hit first: telecom/broadband, insurance, banks, healthcare, subscriptions. Travel sees booking, not negotiation.

## 2. How companies respond
- Detect and route, not block. Pindrop BotStopper launched 2026-09-16. It identifies "which agent is calling, who it represents and what it should be allowed to do". https://www.globenewswire.com/news-release/2026/09/16/3363204/0/en/pindrop-launches-pindrop-botstopper-technology-to-detect-ai-voice-agents-for-the-enterprise.html
- Web: Cloudflare "signed agents" via Web Bot Auth (Aug 2025: ChatGPT agent, Goose, Browserbase, Anchor). https://blog.cloudflare.com/signed-agents/ . Visa Trusted Agent Protocol (Oct 2025) and Mastercard Agent Pay cover payments. HUMAN AgenticTrust adds a behavioral layer [U] https://eco.com/support/en/articles/15192003-mastercard-agent-pay-vs-visa-trusted-agent-2026-compared
- Adapt: UCP launched 2026-01-11 and now includes Amazon, Meta, Microsoft, Salesforce, and Stripe on its council. Its discount extension carries codes, not negotiation. https://ucp.dev/2026-01-23/specification/discount/ , https://stripe.com/blog/three-agentic-commerce-trends-nrf-2026
- No company publicly offers agents negotiated terms.
- Regulation: EU AI Act Art. 50 disclosure applies since 2026-08-02, not delayed. https://www.joneswalker.com/en/insights/blogs/ai-law-blog/yes-august-2-still-matters-the-eu-approved-a-high-risk-ai-delay-but-most-trans.html?id=102nbon . The FCC/TCPA AI-voice rules target outbound robocalls, not consumer agents calling a business. State disclosure rules exist in CA, CO, UT, and TX [U] https://justcall.io/blog/ai-voice-agent-disclosure-laws.html . California AB 2863 (July 2025): a retention offer must sit beside a click-to-cancel button. So a cancel agent can refuse the offer at no cost. https://btlaw.com/en/insights/alerts/2025/california-expands-automatic-renewal-law-new-requirements-now-in-effect

## 3. Who builds the company side
| Layer | Players | Note |
|---|---|---|
| Agent detection | Pindrop, Cloudflare, HUMAN, Akamai, DataDome | Pindrop already frames "what it may do" |
| Agent checkout | Shopify Agentic Storefronts (all US, 2026-03-24), Agentforce Commerce GA, Stripe ACS, commercetools | https://cxtoday.com/salesforce-agentforce-commerce-generally-available |
| CX agents | Sierra ($150M ARR Feb 2026; $15.8B valuation [U]), Decagon ($250M Series D at $4.5B, Jan 2026) | They already run retention offers. https://sacra.com/c/decagon/ |
| Offer and negotiation engines | Nibble ($3.3M seed, 30K negotiations/month, $499/mo on Shopify), Churnkey, ProsperStack, Chargebee Retention | Built for human shoppers, not agents. https://apps.shopify.com/nibble-chat-bot |

## 4. White space
Unowned: one endpoint that (a) recognizes the agent, (b) verifies whose account and what mandate, (c) checks claims such as a competitor quote, (d) concedes inside margin, retention, and LTV rules, and (e) writes a binding, auditable offer record. Everyone else stops one step short. Pindrop stops at "allowed to do". UCP stops at codes. Sierra and Decagon negotiate with no agent-specific policy or proof of claims.
- B2C: the retention desk pays (VP Retention or Care). Budget line: save-offer spend plus contact-center cost. The pain is concession leakage. Agents ask every time and never get tired.
- B2B: deal desk and CRO pay (CPQ discount authority). Salesforce absorbs it.
- Absorption risk is high: Sierra or Decagon adds an agent-caller policy, Pindrop adds mandate checks. The defensible part is cross-company claim verification (competitor quote proof, a shared registry of agent concessions). A network, not a feature.

## 5. Scores
| Criterion | Score | Why |
|---|---|---|
| Volume today | 2 | ~1/80 calls, mixed with fraud. Consumer negotiating agents about 4 weeks old |
| Pain/loss | 3 | Retention leakage is real but unmeasured. Stock reaction [U] |
| White space | 3 | Narrow. Policy plus claim verification is open |
| Budget clarity | 2 | Spans CX, retention, and pricing. No line item yet |
| Venture path | 3 | Big if agent calls reach 10%+. Today it is a feature |
| Absorption resistance | 2 | Sierra, Decagon, Pindrop, Salesforce are adjacent |
| **Total** | **15/30** | |

## Beachhead and 2-week test
Beachhead: US regional broadband/cable retention. Internet bills are a headline Muse use case. Wide promo bands. Regional ISPs are less vendor-locked than carriers. SEA agent volume looks too thin today (judgment, no data found).

Test (2026-10-05 to 10-16):
1. Days 1-3: run Muse or Gemini against retention lines at 8 ISPs on accounts held by you or consenting friends, with AI disclosure. Log offer rate and size against a human-caller control.
2. Days 3-10: book 15 calls with named heads of retention or care at Astound, WOW!, Sparklight/Cable One, Breezeline, Ziply, Mediacom, and similar. Ask: can you count agent calls today? What did agents extract last quarter? Will you pay for a policy-bounded endpoint?
3. Days 10-14: ask for a paid 60-day pilot at $5K or more.

Kill criterion: drop the idea if fewer than 5 of 15 can name an agent-call number or a concession they worry about, or if no one commits to a paid pilot. Then reframe as a feature for Pindrop or Sierra.
