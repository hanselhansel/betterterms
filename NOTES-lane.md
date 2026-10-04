# Lane r2d notes: inbound period null regression

Things outside this lane's file list that the orchestrator may want:

- `docs/decisions/0016-quote-rule-and-gate-fixes.md` item C still says a
  present-null `period` on the inbound file is a broken file. This lane
  relaxed exactly that for inbound.yaml (`period: null` = "not stated",
  like an absent key). A one-line amendment to 0016 would keep the
  record accurate; not done here because the decision docs are assigned
  to the docs lane.
- The draft file's bad-period block reason keeps the old wording
  "period must be once, month or year" (gate.py, reported in `reasons`,
  not as an exit-2 input error). Gate reasons carry no file prefix and
  the draft path is caller-chosen, so "draft.yaml" would guess wrong.
- `btlib/sources.py` already treats `period: null` as "once" for
  source records (agent-written stdin, same shape as inbound). Its
  error text "source record: period must be once, month or year" already
  names the field, so it was left unchanged.
