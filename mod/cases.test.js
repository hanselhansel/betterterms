// Case-decision tests for lib/cases.js. Run: node --test mod/

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as C from "./lib/cases.js";
import * as IO from "./lib/hostio.js";
import { hostOf } from "./register.js";
import {
  BRIEF, BT, CASE_ID, DIR, DRAFT, GATE, GATE_BLOCK, GATE_NEEDS_APPROVAL,
  RENDERED, THREAD, fakeDollar,
} from "./testkit.js";

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

  test("the band counts drafts whose saved gate passed and are unsent", () => {
    const gated = {
      ...base,
      draftText: DRAFT,
      draftMtimeMs: 10,
      gateText: GATE,
      gateMtimeMs: 11,
      threadText: THREAD,
      threadMtimeMs: 1,
    };
    const c = C.deriveCase(gated);
    assert.equal(c.pending, true);
    assert.equal(c.needsApproval, false);
    const flagged = { ...gated, gateText: GATE_NEEDS_APPROVAL };
    assert.equal(C.deriveCase(flagged).pending, true);
    assert.equal(C.deriveCase(flagged).needsApproval, true);
    // gate.json's hash is the case's current held-draft hash: the
    // pane's approve refuses any held record that does not match it.
    const held = `{"result":"needs_approval","reasons":[],"rendered":"x","hash":"${"f".repeat(64)}"}`;
    assert.equal(C.deriveCase({ ...gated, gateText: held }).gateHash, "f".repeat(64));
    assert.equal(C.deriveCase(gated).gateHash, null);
    // A block, a missing verdict and a gate that ran before the last
    // draft write all leave the draft out of the band.
    assert.equal(C.deriveCase({ ...gated, gateText: GATE_BLOCK }).pending, false);
    assert.equal(C.deriveCase({ ...gated, gateText: undefined }).pending, false);
    assert.equal(C.deriveCase({ ...gated, gateText: "not json" }).pending, false);
    assert.equal(C.deriveCase({ ...gated, gateMtimeMs: 5 }).pending, false);
    // A sent draft (a newer thread entry) and a closed case never count.
    assert.equal(C.deriveCase({ ...gated, threadMtimeMs: 20 }).pending, false);
    assert.equal(C.deriveCase({ ...gated, closed: true }).pending, false);
  });

  test("next action names the pending step", () => {
    assert.equal(C.deriveCase(base).next, "finish intake");
    assert.equal(C.deriveCase({ ...base, sourceCount: 1 }).next, "draft the first message");
    const inbound = `## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;
    assert.equal(C.deriveCase({ ...base, threadText: inbound }).next, "draft the reply");
    assert.equal(C.deriveCase({ ...base, threadText: THREAD }).next, "await their reply");
    assert.equal(C.deriveCase({ ...base, threadText: THREAD, closed: true }).next, "closed");
    const pending = {
      ...base,
      threadText: inbound,
      draftText: DRAFT,
      draftMtimeMs: 9,
      gateText: GATE_NEEDS_APPROVAL,
      gateMtimeMs: 10,
      threadMtimeMs: 1,
    };
    assert.equal(C.deriveCase(pending).next, "approve the draft");
    assert.equal(C.deriveCase({ ...pending, gateText: GATE }).next, "send the draft");
    assert.equal(C.deriveCase({ ...pending, gateText: undefined }).next, "gate the draft");
    assert.equal(C.deriveCase({ ...pending, gateText: GATE_BLOCK }).next, "gate the draft");
  });
});

describe("findSend", () => {
  const cases = [{ id: CASE_ID, rendered: RENDERED, stage: "exchange" }];

  test("flags a call whose payload carries the rendered gate text", () => {
    const hit = C.findSend([`mail vendor@x <<EOF\n${RENDERED}\nEOF`], cases);
    assert.equal(hit.id, CASE_ID);
  });

  test("flags a payload containing the render inside more text", () => {
    const hit = C.findSend([`curl -d 'body=${RENDERED}   extra' hook`], cases);
    assert.equal(hit.id, CASE_ID);
  });

  test("ignores unrelated payloads, missing renders and closed cases", () => {
    assert.equal(C.findSend(["ls -la", "echo hello"], cases), null);
    assert.equal(C.findSend([], cases), null);
    assert.equal(C.findSend([RENDERED], [{ id: CASE_ID, rendered: null }]), null);
    const closed = [{ id: CASE_ID, rendered: RENDERED, stage: "closed" }];
    assert.equal(C.findSend([`send ${RENDERED}`], closed), null);
  });

  test("a very short render needs the case id in the payload", () => {
    const short = [{ id: CASE_ID, rendered: "ok" }];
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

  test("needs_approval holds the draft for the Approvals tab", () => {
    const v = C.decideSend(
      { result: "needs_approval", reasons: ["action 'cancel' requires --approved"], hash: "f".repeat(64) },
      { ...c, action: "cancel", autonomy: 4 },
    );
    assert.equal(v.kind, "held");
    assert.equal(v.hash, "f".repeat(64));
    assert.equal(C.decideSend({ result: "needs_approval", reasons: [] }, c).hash, null);
  });
});

// The sendShapeError key-class suite moved to sendshape.test.js when
// the rule gained key classes (subject/title, address/id, content,
// everything else).

describe("bt.py resolution", () => {
  const REL = "skills/betterterms-guardrails/scripts/bt.py";
  const MROOT = "/cache/betterterms/betterterms-mod/0.10.0";

  test("finds the core plugin two levels up in the marketplace cache", async () => {
    // Marketplace plugins install to cache/<market>/<plugin>/<version>;
    // the mod's own version differs from the core plugin's, so the
    // sibling's version dir is discovered by listing, not guessed.
    const installed = `/cache/betterterms/betterterms/0.10.0/${REL}`;
    const { $ } = fakeDollar({
      files: { [installed]: "#!" },
      dirs: {
        "/cache/betterterms/betterterms": [
          { name: "0.9.0", kind: "dir", isLink: false },
          { name: "0.10.0", kind: "dir", isLink: false },
        ],
      },
    });
    $.plugin.root = MROOT;
    assert.equal(await IO.findBt(hostOf($)), installed);
  });

  test("the in-repo sibling skills dir still resolves", async () => {
    const { $ } = fakeDollar({ files: { [BT]: "#!" } });
    assert.equal(await IO.findBt(hostOf($)), BT);
  });
});

describe("labels", () => {
  test("band and toast text", () => {
    assert.equal(C.bandText(1, 0, []), "1 draft waiting");
    assert.equal(C.bandText(0, 3, []), "3 drafts waiting");
    assert.equal(C.bandText(1, 1, ["Comcast"]), "Comcast replied, 2 drafts waiting");
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
