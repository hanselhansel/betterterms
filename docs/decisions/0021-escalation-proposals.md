# 0021. Stopped turns may carry a proposal, always held for approval

Status: accepted, owner decision. Date: 2026-10-07.

## Context

The score bands `unknown`, `near_floor` and `below_floor` and any
non-empty escalate list used to end the exchange turn outright: the
exchange skill forbade writing `draft.yaml` on those turns, so the
only product-legal outcome was a bare hand to the user. That made a
whole class of normal turns silent -- a below-target offer, a
message with no parseable number, a polite "are you an AI?" -- where
the useful move is a draft the user can approve or reject, not a
dead stop. The eval suite was written against that behavior and
expected useful proposed replies the skill could not produce.

## Decisions

- A stopped turn pauses autonomous action, it does not forbid
  drafting. Two shapes are legal: one safe proposal drafted from
  the plan and gated as usual, or a recommendation-only hand to the
  user when no draft is useful or safe.
- The gate enforces the hold in code, not the prompt: with
  `--inbound` supplied, `gate.check` rescores the message itself
  (`btlib.escalate` wraps `btlib.score.classify`) and adds a review
  finding when the real band is a stop band, the escalate list is
  non-empty, or the scorer refuses the message outright. A band or
  flag written into `inbound.yaml` is data, never consulted.
- The finding is one generic reason, `the counterparty's message
  needs your review`: no number, band or flag, so a held proposal
  leaks nothing about the floor's value, direction or distance.
- The hold rides the existing held/hash/consume path unchanged:
  the draft is parked as `held/<hash>.yaml`, only a user action
  writes the `.approved` marker bound to the exact send tuple, and
  it is spent once. A changed text, a changed tuple or a second
  send is held again.
- Block still dominates: a draft that breaks a hard rule on a
  stopped turn reports only its block reasons and can never be
  approved. A supplied inbound the scorer cannot classify holds
  rather than passing -- an unscorable turn is never grounds for
  an autonomous send. An opening turn carries no inbound and is
  untouched.
- The eval contract matches production: a draft on a stopped turn
  still runs `bt.py gate` and must come back `needs_approval`;
  a `decision: escalate` block remains legal only when the real
  score justifies it.
