# Call script template

The script the user holds in the live conversation. Fill it from
`plan.yaml` and the impact file before the meeting. It is a user
artifact, not a draft: it never goes through `bt.py gate` because it
is never sent. The same honesty rules still apply: every number and
claim traces to a plan fact or the user's own record, and the floor
never appears in it.

Write it in the user's voice, short enough to say out loud, and keep
it to one page.

## Shape

### 1. Opening line

One warm sentence that names the purpose and the relationship.
Relational framing, per playbook move 7:

```text
I want to talk about my role and pay. I want to keep growing here,
and I would like us to find a way to make this work for both of us.
```

### 2. The ask

One sentence, a precise figure or a range that climbs from the
target, hedged but direct (playbook move 5):

```text
Based on my results this year and the market data I have, I am
asking for <target or range, from plan.yaml>.
```

### 3. The reasons

Three impact lines, each a number or a dated result from the impact
file. Example shapes:

```text
In the last year I <result with a number, for example shipped X or
grew Y>.
I took on <scope that grew: team size, revenue line, new area>.
The market range for this level is <fact id from plan.yaml, cited
source only>.
```

### 4. The equal options

Two or three options worth the same to the user, different in shape
for the company (playbook move 6):

```text
I see a few ways to get there:

Option one: <label>: <terms>.
Option two: <label>: <terms>.
Option three: <label>: <terms>.

Each of these fits. Which can we do?
```

### 5. The five likeliest objections and the answers

Draft the answer to each before the meeting, in the user's words:

1. "The budget is set." Acknowledge, then ask what the cycle allows:
   a dated review, a mid-cycle correction, or a non-cash option now.
2. "You are at the top of the band for your level." That is the case
   for the level change: pivot to the promotion argument and the
   level mapping in the impact file.
3. "You need more time." Ask which specific milestones would close
   the gap, and get them stated concretely.
4. "I need to check with HR / the committee." Agree, hand over the
   one-page case, and set the follow-up date before leaving.
5. "We can do the title but not the money." Take the equal options:
   a dated pay review, a bonus, or an equity refresh.

### 6. The close

Always end asking for the result in writing or a dated next step:

```text
Thank you. Can you send me what we covered in writing, or shall we
set a date to pick this back up?
```

## Rules for filling it

- The ask, options, and ladder come from `plan.yaml`. Nothing else
  sets a number.
- Reasons come from the impact file. Claims the user cannot back up
  stay out.
- Peer names and peer salaries stay out unless the peer offered the
  number and the user chooses to share it.
- Never script the floor, a walk-away threat the user will not act
  on, or an outside offer that is not real and written.
