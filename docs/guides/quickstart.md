# Quickstart

Two journeys cover the kit: Act for written exchanges, Coach for live
conversations. Both start the same way: a command, a short intake, and a
walk-away number you type in your own terminal.

## Journey 1: lower a subscription (Act)

1. Run `/betterterms:subscriptions`. Not sure which pack fits? Run
   `/betterterms` and say what you want to improve.
2. Intake asks what a good result looks like, what the worst deal you would
   still take is, what it may never disclose, your deadline, and how much
   autonomy it gets. It ends with a ranking check: you order three sample
   outcomes so it can confirm it read your priorities right.
3. Set your walk-away number. The skill prints a command; run it in your own
   terminal:

   ```
   python3 ../betterterms-guardrails/scripts/bt.py case set-floor <case_id>
   ```

   It prompts `Walk-away number (hidden): ` and does not echo. The value lands
   in a file only the gate and scorer read. The model never sees it.
4. Discovery says what it wants to read (receipts, renewal notices, price-change
   mail, any statements you drop in) and asks permission per source. It returns
   a target list: counterparty, amount, cadence, renewal date, evidence.
5. Pick the targets. Research reads each vendor's cancellation, refund, and
   pricing policy, current promotions, recent first-hand reports, and your
   rights. Every fact lands in a source record with a URL and the date read.
6. Plan gives you the target price, two or three equal options, and a
   concession ladder. The floor stays in code.
7. Exchange drafts each message in your voice. At the default autonomy you
   approve every send. Inbound replies get parsed, scored against your
   priorities, checked against the fact list, and answered.
8. Accept, cancel, pay, sign, and dispute always wait for your explicit yes.
   When the case closes, the ledger records the saving.
   `bt.py ledger total` answers "how much have I saved".

## Journey 2: negotiate a job offer (Coach)

1. Run `/betterterms:salary`.
2. Intake captures the full offer (base, bonus, equity type and vesting, level,
   start date), the deadline, your other processes, your priorities, and your
   walk-away number through the same hidden terminal prompt. Default autonomy
   is level 1: drafts only, you speak.
3. Discovery reads the offer letter and recruiter emails only if you allow it.
4. Research gathers comp data, the company's leveling and policies, and recent
   negotiation reports. Comp numbers come from what you supply plus cited
   public sources.
5. Plan fixes the ask, the package, and the trade-offs before any call. You
   commit to the numbers here, not mid-conversation.
6. Coach writes your call script: the opening line, the ask as a precise
   figure, your reasons, two or three equal package options, answers to the
   five likeliest objections, and the closing request to get it in writing.
7. Rehearse. The agent plays the recruiter with realistic pushback, then scores
   your delivery against the script.
8. Have the live conversation. Then debrief: what was offered, an updated plan,
   and a drafted follow-up email. The ledger records final versus initial
   package.

## What a turn looks like in Act mode

Each inbound message produces `inbound.yaml` (the counterparty's offer, its
text, the amounts it stated). The scorer bands the offer against your target
and floor. The agent picks one move, writes `draft.yaml` with a template and
placeholders instead of typed prices, and runs `bt.py gate`. On `pass` the
rendered text is what goes out, verbatim. On `block` it redrafts once or
escalates. On `needs_approval` it asks you first.
