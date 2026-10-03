// Case-decision tests for lib/cases.js. Run: node --test mod/

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as C from "./lib/cases.js";
import { BRIEF, DRAFT, THREAD, CASE_ID, DIR } from "./testkit.js";

describe("deriveCase", () => {
  const base = { id: CASE_ID, briefText: BRIEF, threadText: "", sourceCount: 0, closed: false };

  test("pipeline stages", () => {
    assert.equal(C.deriveCase(base).stage, "found");
    assert.equal(C.deriveCase({ ...base, sourceCount: 2 }).stage, "researched");
    const inbound = `## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;
    assert.equal(C.deriveCase({ ...base, threadText: inbound }).stage, "exchange");
    assert.equal(C.deriveCase({ ...base, threadText: THREAD }).stage, "waiting");
    assert.equal(C.deriveCase({ ...base, threadText: THREAD, closed: true }).stage, "closed");
  });

  test("autonomy falls back to the mode default", () => {
    assert.equal(C.deriveCase(base).autonomy, 2);
    const coach = BRIEF.replace("mode: act", "mode: coach").replace("autonomy: 2", "autonomy: 1");
    assert.equal(C.deriveCase({ ...base, briefText: coach }).autonomy, 1);
  });

  test("a fresh draft waits for approval only when autonomy or action says so", () => {
    const withDraft = {
      ...base,
      draftText: DRAFT,
      draftMtimeMs: 10,
      threadMtimeMs: 1,
      threadText: THREAD,
    };
    assert.equal(C.deriveCase(withDraft).needsApproval, true);
    const aut4 = BRIEF.replace("autonomy: 2", "autonomy: 4");
    assert.equal(C.deriveCase({ ...withDraft, briefText: aut4 }).needsApproval, false);
    const irreversible = DRAFT.replace("action: send", "action: cancel");
    assert.equal(C.deriveCase({ ...withDraft, briefText: aut4, draftText: irreversible }).needsApproval, true);
    assert.equal(C.deriveCase({ ...withDraft, draftMtimeMs: 1, threadMtimeMs: 10 }).needsApproval, false);
  });

  test("next action names the pending step", () => {
    assert.equal(C.deriveCase(base).next, "finish intake");
    assert.equal(C.deriveCase({ ...base, sourceCount: 1 }).next, "draft the first message");
    const inbound = `## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;
    assert.equal(C.deriveCase({ ...base, threadText: inbound }).next, "draft the reply");
    assert.equal(C.deriveCase({ ...base, threadText: THREAD }).next, "await their reply");
    assert.equal(C.deriveCase({ ...base, threadText: THREAD, closed: true }).next, "closed");
    const pending = { ...base, threadText: inbound, draftText: DRAFT, draftMtimeMs: 9, threadMtimeMs: 1 };
    assert.equal(C.deriveCase(pending).next, "approve the draft");
  });
});

describe("findSend", () => {
  const DRAFT_TEXT = C.parseFlatYaml(DRAFT).text;
  const cases = [{ id: CASE_ID, draftText: DRAFT_TEXT }];

  test("flags a call whose payload carries the draft text", () => {
    const hit = C.findSend([`mail vendor@x <<EOF\n${DRAFT_TEXT}\nEOF`], cases);
    assert.equal(hit.id, CASE_ID);
  });

  test("flags a payload containing the draft inside more text", () => {
    const hit = C.findSend([`curl -d 'body=${DRAFT_TEXT}   extra' hook`], cases);
    assert.equal(hit.id, CASE_ID);
  });

  test("ignores unrelated payloads", () => {
    assert.equal(C.findSend(["ls -la", "echo hello"], cases), null);
    assert.equal(C.findSend([], cases), null);
    assert.equal(C.findSend([DRAFT_TEXT], [{ id: CASE_ID, draftText: null }]), null);
  });

  test("a very short draft needs the case id in the payload", () => {
    const short = [{ id: CASE_ID, draftText: "ok" }];
    assert.equal(C.findSend(["send ok"], short), null);
    assert.equal(C.findSend([`reply ok to ${CASE_ID}`], short).id, CASE_ID);
  });
});

describe("gateArgv", () => {
  test("builds the gate argv", () => {
    assert.deepEqual(C.gateArgv("/bt.py", DIR, CASE_ID, {}), [
      "python3", "/bt.py", "gate", CASE_ID, "--draft", `${DIR}/draft.yaml`,
    ]);
    assert.deepEqual(C.gateArgv("/bt.py", DIR, CASE_ID, { inbound: true, approved: true }), [
      "python3", "/bt.py", "gate", CASE_ID, "--draft", `${DIR}/draft.yaml`,
      "--inbound", `${DIR}/inbound.yaml`, "--approved",
    ]);
  });
});

describe("decideSend", () => {
  const c = { id: CASE_ID, action: "send", autonomy: 2 };
  const pass = { result: "pass", reasons: [] };

  test("block and error deny", () => {
    assert.equal(C.decideSend({ result: "block", reasons: ["floor disclosed"] }, c).kind, "deny");
    assert.match(C.decideSend({ result: "block", reasons: ["floor disclosed"] }, c).reason, /floor/);
    assert.equal(C.decideSend({ result: "error", reasons: ["no file"] }, c).kind, "deny");
    assert.equal(C.decideSend(null, c).kind, "deny");
  });

  test("pass respects autonomy", () => {
    assert.equal(C.decideSend(pass, { ...c, autonomy: 1 }).kind, "deny");
    assert.equal(C.decideSend(pass, c).kind, "ask");
    assert.equal(C.decideSend(pass, { ...c, autonomy: 3 }).kind, "allow");
    assert.equal(C.decideSend(pass, { ...c, autonomy: 4 }).kind, "allow");
  });

  test("needs_approval asks and re-gates with --approved", () => {
    const v = C.decideSend(
      { result: "needs_approval", reasons: ["action 'cancel' requires --approved"] },
      { ...c, action: "cancel", autonomy: 4 },
    );
    assert.equal(v.kind, "ask");
    assert.equal(v.reapprove, true);
  });
});

describe("labels", () => {
  test("band and toast text", () => {
    assert.equal(C.bandText(1), "1 draft waiting for approval");
    assert.equal(C.bandText(3), "3 drafts waiting for approval");
    assert.equal(C.toastText(CASE_ID, 1), `New reply in ${CASE_ID}.`);
    assert.equal(C.toastText(CASE_ID, 2), `2 new replies in ${CASE_ID}.`);
  });

  test("safeCaseId holds the allowlist", () => {
    assert.equal(C.safeCaseId(CASE_ID), true);
    assert.equal(C.safeCaseId(".."), false);
    assert.equal(C.safeCaseId("a/b"), false);
    assert.equal(C.safeCaseId(".hidden"), false);
  });
});
