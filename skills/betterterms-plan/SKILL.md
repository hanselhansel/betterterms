---
name: betterterms-plan
description: Builds the plan for a betterterms case. Sets the target, two or three equal options, a shrinking concession ladder, a patience budget, timing, channel, and the fact list a draft may use. Use after intake and research, before any message is drafted, when the user is ready to set strategy.
---

# betterterms-plan

You set the numbers and the moves before any message is drafted. The model
sees the target; the floor stays in code.

## Inputs

- `brief.yaml` in the case folder: goals, ranked priorities, autonomy,
  deadline, never_disclose.
- The case folder's `sources/` records: dated quotes with trust levels.
- The negotiation principles in `references/principles.md`. Follow them;
  they carry the evidence.

## Outputs

- `plan.yaml` in the case folder with: `target`, `currency`, `options`
  (two or three equal options, each `{label, value, terms}`), `ladder`
  (a list of `{value, reason}`, shrinking steps), `patience`
  (`{rounds, days}`), `timing`, `channel`, and `facts` (a list of
  `{id, text, source}`).

## Procedure

1. Set the target from the user's goals and the researched prices.
   - Pay direction (bills, fees, purchases): lower is better.
   - Receive direction (offers, raises, refunds owed): higher is better.
2. Do not open or quote the floor file. Only `bt.py gate` and `bt.py
   score` read it. `plan.yaml` never holds a floor.
3. Choose the opening move. Anchor first on the target when the market is
   known. Let them move first when it is not, or when your offer would
   reveal priorities.
4. Build two or three equal options the user would accept (MESOs). Vary
   the terms, keep the value equal.
5. Build the concession ladder: shrinking steps, each with a reason.
6. Set the patience budget in rounds and calendar days. Set the timing
   (for example promo end, vendor quarter end, budget cycle) and the
   channel.
7. Write the fact list: every factual claim a draft may make, each linked
   to a source record or a user statement. Drafts may only claim facts on
   this list.
8. Write `plan.yaml`, then read the case back:

   `python3 ../betterterms-guardrails/scripts/bt.py case show <case_id>`

9. At autonomy level 3 or 4, get the user's explicit approval of the plan
   before any exchange begins.
