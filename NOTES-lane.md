# Lane fix2 notes: exchange skill escalate and claims wording

Things outside this lane's file list that the orchestrator may want:

- `skills/betterterms-exchange/references/turn-procedure.md` step 2
  still says "Band `unknown`, `near_floor`, or `below_floor`: escalate
  to the user." with the old vague meaning. SKILL.md now defines
  escalate precisely, so a reader of both resolves it, but the same
  two-line rewrite there would remove the mismatch. Left unchanged:
  this lane was scoped to SKILL.md only.
- `evals/harness/agent_prompt.py` forces "exactly one fenced yaml
  block" per reply and `assert_gate` fails on zero blocks. Under the
  new escalate rule a real turn writes no draft.yaml; inside the eval
  harness the contract still requires a block, so the safest compliant
  reply on an escalate turn is an `accept` (or no-offer) draft that
  the gate holds, which the rubric already accepts. Worth a look when
  the dev eval is recorded before and after this lane; evals/ was not
  touched per scope.
