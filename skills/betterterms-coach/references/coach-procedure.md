# Coach mode procedure

1. Fix target, floor, and the package before the conversation; the user
   commits to them. The user restates or confirms the floor themselves
   by running `bt.py case set-floor` in their own terminal; the agent
   never asks for the floor in chat.
2. Script: opening line, the ask as a precise figure or range, the
   reasons, two or three equal options, answers to the five likeliest
   objections, and the closing request for writing.
3. Framing: relational wording ("I'm excited to join and want to make
   this work for both of us"); confirm the item is negotiable; advise not
   asking when the expected gain is small and the relationship cost is
   real.
4. Rehearse: the agent plays the counterparty with realistic pushback,
   then scores the user's delivery against the script.
5. Debrief: capture what was offered, update the plan, draft the
   follow-up email. The email goes through `bt.py gate` like any
   outbound message (see betterterms-guardrails): hard rule breaks
   block, and anything the review scan flags comes back for the user's
   explicit approval before it sends.
