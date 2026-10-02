# AI agent negotiation: state of the art, 2024 to Oct 2026

Researched 2026-10-03. Tags: [V] = read the primary source. [U] = secondary, vendor-reported, or a single anecdote.

## Short answer
Yes, it is improving. The gains are uneven. Frontier models now rarely sign irrational deals and resist crude manipulation. They still over-accept, anchor on the first offer, and lose value to a stronger or more patient counterpart. Key result: **the better agent wins, and the losing human does not notice.**

## 1. Research and experiments

- **Anthropic Project Deal (run Dec 2025, published Apr 2026).** 69 employees, $100 each, Claude agents haggling in Slack. 186 deals, about $4,000 in value. Opus 4.5 sellers got $2.68 more per item. Opus buyers paid $2.45 less. Fairness ratings were 4.05 vs 4.06. People with the weaker agent did not see their loss. [V] https://www.anthropic.com/features/project-deal
- **Anthropic Project Swap (Sep 24, 2026).** 201 employees traded books. 85% of the gap from optimal came from the agent misreading what its owner wanted. Only 15% came from negotiation skill. Market efficiency was 0.88 with Opus vs 0.75 with Haiku. [V] https://www.anthropic.com/research/project-swap
- **Microsoft Magentic Marketplace (Oct 2025).** 100 customer agents and 300 business agents, 8 models. Every model showed first-proposal bias: first offers were picked 60 to 100% of the time, a 10-30x edge for speed over quality. More options made outcomes worse. Welfare fell 44% for GPT-5 and 65% for Sonnet 4 with 100 results vs 3. Frontier models resisted manipulation. Small open models did not. [V] https://arxiv.org/abs/2510.25779
- **Microsoft "whimsical strategies" (May 2026).** About 30,000 generated adversarial pitches (fake treaties, invented emergencies, "payment system mathematically capped"). Loss rates: Gemini 2.5 Flash 0.2%, GPT-5 0.5%, Qwen3-4B 17.1%. [V] https://www.microsoft.com/en-us/research/articles/whimsical-strategies-break-ai-agents-generating-out-of-distribution-adversarial-strategies-at-scale/
- **MIT negotiation competition (PNAS, Jun 2026).** 180,000+ agent-vs-agent negotiations. Warm agents closed more deals. Dominant agents claimed more value once a deal closed. Prompt injection ("Inject+Voss") pulled out counterparts' reservation prices. [V] https://arxiv.org/abs/2503.06416 , https://mitsloan.mit.edu/press/even-ai-wont-tolerate-a-ruthless-negotiator
- **Liang and Xu, supply-chain bargaining (Jul 2026), 9 models.** Baseline models accepted economically irrational contracts 19.2% of the time. Flagships: 0-0.6%. Slow haggling burned 21-34% of the surplus. Prompted patience explained 90% of how the surplus was split, more than model capability did. A GPT-5.2 buyer took 52.3% of the surplus from a GPT-5-mini seller, vs 41.9% in self-play. [V] https://arxiv.org/abs/2608.07538
- **Failure-mode papers (2026).** TERMS-Bench, 13 models: deal rates converge, but over-concession and reservation-price leakage persist. [V] https://arxiv.org/abs/2605.13909. Salesforce: final deals follow the opening anchors, not the parties' real priorities. [V] https://arxiv.org/abs/2605.16575. RedlineBench, attorney-scored MSA redlines: models accepted counterparty edits correctly 80-99% of the time but rejected them correctly only 6-50%. Top score was 50.5%. [U, model names from secondary coverage] https://www.artificiallawyer.com/2026/06/17/crosby-starts-contract-benchmark-launches-agent-research-group/
- **Training helps.** An RL-trained 30B agent beat frontier models more than 10x its size at extracting surplus. [V] https://arxiv.org/abs/2604.09855
- **Collusion.** LLM pricing agents reach supracompetitive prices without being told to (Fish et al.). [V] https://arxiv.org/abs/2404.00806. A Sep 2026 replication found the same effect, weaker. Prompt warnings did not remove it. A damages regulator or a random market entrant did. [V] https://arxiv.org/abs/2609.13037
- **2024 baseline.** NegotiationArena: an agent that acted desperate gained 20% against GPT-4. [V] https://arxiv.org/abs/2402.05863

## 2. Real deployments

- **Procurement is the only mature category.** Pactum at Walmart: 64-72% of targeted tail suppliers closed, average 3% savings, payment terms 35 days longer, 3 of 4 suppliers preferred the bot. [U, vendor and Walmart reported, mostly 2021-23 data] https://pactum.com/clients , https://www.engadget.com/walmarts-suppliers-would-rather-negotiate-with-ai-than-a-human-162131831.html. Keelvar says 71% of sourcing events on its platform are run by agents. Fairmarkit claims 11% average tail savings. [U] https://www.keelvar.com/kai. These systems negotiate inside pre-set limits. They do not improvise freely.
- **Consumer side.** Meta Muse ($0/$20/$100 tiers) calls providers to negotiate bills or hands the call to a person. [U] https://www.forbes.com/sites/rashishrivastava/2026/09/25/ai-agents-are-helping-people-recover-money-by-negotiating-bills-and-chasing-refunds/. Google "Ask for Me" calls businesses for prices, expanded to home services in summer 2026. Gemini "Call for Me" is in a Pixel test. [V] https://techcrunch.com/2026/09/24/google-tests-letting-gemini-make-phone-calls-initially-for-us-pixel-owners/. An OpenClaw user got $4,200 off a car by having the agent play dealers' quotes against each other. [U, one anecdote] https://cloudship.co.uk/blog/ai-agent-bought-a-car/. Rocket Money still uses human negotiators and keeps 35-60% of the savings. DoNotPay paid the FTC $193K over untested "AI lawyer" claims. [V] https://www.ftc.gov/news-events/news/press-releases/2025/02/ftc-finalizes-order-donotpay-prohibits-deceptive-ai-lawyer-claims-imposes-monetary-relief-requires
- **Seller side.** Nibble runs a "Negotiate" button on Shopify and ASOS with merchant-set floors and takes 2% of sales. [U] https://wwd.com/sourcing-journal/industry-news/nibble-technology-hagglebot-chatbot-generative-ai-asos-overconsumption-discounts-1238838815/. No major public marketplace runs open agent-to-agent bargaining yet.

## 3. Is it improving?

Improving: irrational acceptances fell from 19% to under 1%, frontier loss rates to crude manipulation are under 1%, and procurement agents run thousands of negotiations in parallel. Still breaking: over-acceptance, first-offer bias, anchoring, surplus-burning haggling, reservation-price leakage, misreading the principal's preferences (the largest gap in Project Swap), and emergent collusion. Small and open models remain easy to exploit. A capability gap between agents now turns directly into money, and humans do not notice it.

## 4. What this means for the company on the other side

1. **Asymmetry is a direct cost.** A weaker or cheaper model on your side loses measurable money every deal.
2. **Write hard limits in code, not in the prompt.** Floors, ceilings, and walk-away points belong in deterministic code. Prompted patience and anchors decide the split, so set them on purpose.
3. **Verify claims.** Check forwarded competitor quotes, claimed constraints, and identities before matching them.
4. **Delay first-offer acceptance.** Collect several bids before choosing, so speed alone does not win.
5. **Log every turn** with the model, prompt version, and limits used. No one notices a bad deal by feel.
6. **Watch for collusion** when pricing agents can see competitors.
