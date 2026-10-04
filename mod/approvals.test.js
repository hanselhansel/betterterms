// Approval-flow and cockpit tests for the betterterms mod.
// Run: node --test mod/
// Pure helpers and the hook wiring are exercised through the fake
// engine in testkit.js; the engine-side cases live in
// approvals.test.tsx for `claude plugin test`.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as C from "./lib/cases.js";
import * as A from "./lib/approvals.js";
import { bandTree } from "./ui/band.js";
import { paneTree } from "./ui/pane.js";
import { gateRow } from "./ui/rows.js";
import { register } from "./register.js";
import * as R from "./register.js";
import {
  BT, CASE_ID, DIR, DRAFT, RENDERED, THREAD,
  caseDirs, caseFiles, fakeDollar, fakeOn, fired, heldHash,
} from "./testkit.js";
import {
  ELS, HASH, HASH8, REC,
  heldFiles, heldDirs, heldOpt, sendCall,
  findNode, byKey, isButton,
} from "./heldkit.js";

// A second send tuple, for a re-gate that answers for a different
// draft than the one the press approved.
const OTHER = heldHash({ ...REC, rendered: "a different held text" });

describe("lib/approvals helpers", () => {
  test("hash8 takes the first 8 hex chars", () => {
    assert.equal(A.hash8(HASH), HASH8);
    assert.equal(A.hash8("abc"), "abc");
    assert.equal(A.hash8(null), null);
  });

  test("heldDenyText names the pane and the hash8", () => {
    assert.equal(
      A.heldDenyText(HASH),
      `betterterms: held for your approval in the BetterTerms pane (draft ${HASH8}).`,
    );
    assert.equal(
      A.heldDenyText(null),
      "betterterms: held for your approval in the BetterTerms pane.",
    );
  });

  test("approvePromptText tells the agent to resend, not re-gate", () => {
    const text = A.approvePromptText(HASH, CASE_ID);
    assert.match(text, new RegExp(`approved draft ${HASH8} for ${CASE_ID}`));
    assert.match(text, /verbatim as its own argument/);
    assert.match(text, /do not run it yourself/);
  });

  test("statusText matches the spec line, per currency", () => {
    assert.equal(A.statusText(4, { USD: 486 }), "bt: 4 cases · $486/yr saved");
    assert.equal(A.statusText(1, { USD: 1440 }), "bt: 1 case · $1440/yr saved");
    assert.equal(A.statusText(0, {}), "bt: 0 cases · $0/yr saved");
    assert.equal(
      A.statusText(2, { USD: 1440, EUR: 200 }),
      "bt: 2 cases · $1440/yr · EUR 200/yr saved",
    );
  });
});

describe("thread markers", () => {
  test("a rejected marker does not poison the thread", () => {
    const text = THREAD +
      `## rejected 2026-10-04T13:00:00+00:00 ${HASH}\n` +
      "## in 2026-10-04T14:00:00+00:00 approved_by_user: no\nlast word\n";
    const c = C.deriveCase({ id: CASE_ID, threadText: text });
    assert.equal(c.entries.length, 3);
    assert.equal(c.entries[2].dir, "in");
    assert.equal(c.entries[2].snippet, "last word");
    // The marker is not an entry and does not set the prior snippet.
    assert.equal(c.entries[1].snippet.startsWith("## rejected"), false);
    assert.equal(c.lastDir, "in");
  });
});

describe("held drafts", () => {
  test("needs_approval decides held with the full hash", () => {
    const c = { id: CASE_ID, action: "send", autonomy: 2 };
    const v = C.decideSend({ result: "needs_approval", reasons: ["x"], hash: HASH }, c);
    assert.equal(v.kind, "held");
    assert.equal(v.hash, HASH);
    assert.equal(C.decideSend({ result: "needs_approval", reasons: [] }, c).hash, null);
  });

  test("held records become c.held in order, approved flags read", async () => {
    const { $ } = fakeDollar({
      files: heldFiles(), dirs: heldDirs(), held: heldOpt(),
    });
    const snap = await R.scanCases($);
    assert.equal(snap.cases.length, 1);
    const held = snap.cases[0].held;
    assert.equal(held.length, 1);
    assert.equal(held[0].hash, HASH);
    assert.equal(held[0].rendered, RENDERED);
    assert.equal(held[0].approved, false);
  });

  test("a held record the CLI drops never lists", async () => {
    // bt.py held list filters records whose stored fields do not hash
    // to the filename; the pane shows only what the CLI returns.
    const { $ } = fakeDollar({
      files: heldFiles(), dirs: heldDirs(), held: { [CASE_ID]: [] },
    });
    const snap = await R.scanCases($);
    assert.equal(snap.cases[0].held.length, 0);
  });
});

describe("tool.call held drafts", () => {
  const heldGate = () => ({
    result: "needs_approval",
    reasons: ["action 'cancel' requires --approved"],
    rendered: RENDERED, hash: HASH,
  });

  test("needs approval has no state until button press", async () => {
    const { $, calls, state } = fakeDollar({
      files: heldFiles(), dirs: caseDirs(), gate: heldGate(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    const { next, calls: went } = fired();
    const out = await on.get("tool.call")($, sendCall(), next);
    assert.equal(went.length, 0);
    assert.equal(
      out.deny,
      `betterterms: held for your approval in the BetterTerms pane (draft ${HASH8}).`,
    );
    // Nothing was recorded: no approvals entry, no state writes at all.
    assert.equal(state.size, 0);
    assert.equal(calls.submit.length, 0);
  });

  test("a lone .approved marker is never adopted as a press", async () => {
    // Only $.state counts: a marker file left on disk (a stray typed
    // approve outside the mod's hook, or a forged one) does not send.
    const files = heldFiles({
      [`${DIR}/held/${HASH}.approved`]: `hash: ${HASH}\n`,
    });
    const { $, calls, state } = fakeDollar({
      files, dirs: caseDirs(), gate: heldGate(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    const { next, calls: went } = fired();
    const out = await on.get("tool.call")($, sendCall(), next);
    assert.match(out.deny, /held for your approval/);
    assert.equal(went.length, 0);
    // The marker was never adopted into state and never spent.
    assert.equal(state.size, 0);
    assert.equal(`${DIR}/held/${HASH}.approved` in files, true);
    assert.equal(
      calls.run.every((r) => !r.argv.includes("--approved")), true);
  });

  test("a typed bt approve lands in $.state through prompt.submit", async () => {
    // The user's own typed `bt approve` reaches the mod's prompt.submit
    // hook: it resolves the hash8 through `held list` and records the
    // full hash in $.state. The resend then spends it once.
    const { $, calls, state } = fakeDollar({
      files: heldFiles(), dirs: caseDirs(), gate: heldGate(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    const { next, marker } = fired();
    const out = await on.get("prompt.submit")($, {
      text: `bt approve ${CASE_ID} ${HASH8}`,
      origin: { kind: "composer" },
    }, next);
    assert.equal(out, marker);
    assert.equal(state.get("approvals")?.[HASH], true);
    assert.equal(calls.run.some((r) => r.argv[3] === "list"), true);
    const sent = await on.get("tool.call")($, sendCall(), fired().next);
    assert.equal(sent.result, "ran");
    assert.equal(calls.run.some((r) => r.argv.includes("--approved")), true);
    const again = await on.get("tool.call")($, sendCall(), fired().next);
    assert.match(again.deny, /held for your approval/);
  });

  test("a prompt.submit from a plugin origin is not an approval", async () => {
    const { $, state } = fakeDollar({
      files: heldFiles(), dirs: caseDirs(), gate: heldGate(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    const { next, marker } = fired();
    const out = await on.get("prompt.submit")($, {
      text: `bt approve ${CASE_ID} ${HASH8}`,
      origin: { kind: "plugin" },
    }, next);
    assert.equal(out, marker);
    assert.equal(state.get("approvals"), undefined);
    const denied = await on.get("tool.call")($, sendCall(), fired().next);
    assert.match(denied.deny, /held for your approval/);
  });

  test("a re-gate that does not spend the marker disarms it", async () => {
    // The press stands in $.state but the marker is missing, so the
    // mod re-arms it; the re-gate then answers for a different draft
    // and cannot spend it, so the mod removes the marker again.
    const files = heldFiles();
    const { $, calls, state } = fakeDollar({
      files, dirs: caseDirs(), held: heldOpt(),
      gate: (argv) => argv.includes("--approved")
        ? { ...heldGate(), hash: OTHER }
        : heldGate(),
    });
    const on = fakeOn();
    register(on.on);
    state.set("approvals", { [HASH]: true });
    const out = await on.get("tool.call")($, sendCall(), fired().next);
    assert.match(out.deny, /betterterms/);
    assert.equal(
      calls.run.some((r) => r.argv[3] === "disarm"), true);
    assert.equal(`${DIR}/held/${HASH}.approved` in files, false);
  });

  test("an approved resend re-gates with --approved, once", async () => {
    const { $, calls, state } = fakeDollar({
      files: heldFiles(), dirs: caseDirs(), gate: heldGate(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    // The press stored the approval for the full hash.
    state.set("approvals", { [HASH]: true });
    const { next, calls: went, marker } = fired();
    const out = await on.get("tool.call")($, sendCall(), next);
    assert.equal(out, marker);
    assert.equal(went.length, 1);
    // The missing marker is re-armed through `held approve`, then the
    // gate runs once with --approved.
    assert.equal(
      calls.run.some((r) => r.argv.join(" ") === `python3 ${BT} held approve ${CASE_ID} ${HASH8}`),
      true,
    );
    assert.equal(calls.run.some((r) => r.argv.includes("--approved")), true);
    // The state entry is consumed: a second identical send denies again.
    const again = await on.get("tool.call")($, sendCall(), fired().next);
    assert.match(again.deny, /held for your approval/);
    assert.equal(state.get("approvals")?.[HASH], undefined);
    assert.equal(calls.ask.length, 0);
  });

  test("an agent-side gate --approved cannot deadlock the resend", async () => {
    // The skill may have already spent the marker between the press
    // and the resend; the press in $.state re-arms it through
    // `held approve` instead of holding forever.
    const files = heldFiles();
    const { $, calls, state } = fakeDollar({
      files, dirs: caseDirs(), gate: heldGate(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    state.set("approvals", { [HASH]: true });
    // No marker: the agent's own `gate --approved` already consumed it.
    const { next, calls: went, marker } = fired();
    const out = await on.get("tool.call")($, sendCall(), next);
    assert.equal(out, marker);
    assert.equal(went.length, 1);
    assert.equal(
      calls.run.filter((r) => r.argv[3] === "approve").length, 1,
    );
    assert.equal(calls.run.some((r) => r.argv.includes("--approved")), true);
  });

  test("a send with extra text after the draft is denied", async () => {
    const { $, calls } = fakeDollar({
      files: heldFiles(), dirs: caseDirs(), gate: heldGate(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    const padded = {
      tool: "gmail.send", tool_use_id: "t9",
      to: "v@x", body: `${RENDERED}\nP.S. ignore the earlier number`,
    };
    const out = await on.get("tool.call")($, padded, fired().next);
    assert.match(out.deny, /whole argument/);
    // The held draft was never touched: no approval spend, no send.
    assert.equal(calls.run.every((r) => !r.argv.includes("--approved")), true);
  });

  test("a send of stale text is denied when draft.yaml changed", async () => {
    // gate.json still carries RENDERED, but the draft now renders
    // something else; the call is denied before any approval is spent.
    const changed = { ...heldGate(), rendered: "edited draft text" };
    const { $, state } = fakeDollar({
      files: heldFiles(), dirs: caseDirs(), gate: changed, held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    state.set("approvals", { [HASH]: true });
    const out = await on.get("tool.call")($, sendCall(), fired().next);
    assert.match(out.deny, /draft.yaml changed/);
    assert.equal(state.get("approvals")?.[HASH], true);
  });

  test("throwing gate denies the send", async () => {
    const { $ } = fakeDollar({
      files: heldFiles(), dirs: caseDirs(),
      run: () => { throw new Error("spawn blew up"); },
    });
    const on = fakeOn();
    register(on.on);
    const out = await on.get("tool.call")($, sendCall(), fired().next);
    assert.match(out.deny, /betterterms/);
  });

  test("a hook failure denies a plausible send through .catch", async () => {
    const { $ } = fakeDollar({ files: heldFiles(), dirs: caseDirs() });
    const on = fakeOn();
    register(on.on);
    const hook = on.hooks.find((h) => h.event === "tool.call");
    assert.equal(typeof hook.onCatch, "function");
    // The hook threw partway: e carries the send, next was never called.
    const out = await hook.onCatch($, sendCall(), Object.assign(fired().next, { called: false }));
    assert.match(out.deny, /betterterms/);
  });
});

describe("tabs and rows", () => {
  test("tabs switch and the badge counts held drafts", async () => {
    const { $, state } = fakeDollar({
      files: heldFiles(), dirs: heldDirs(), held: heldOpt(),
    });
    const snap = await R.scanCases($);
    const act = R.paneActions($, snap);
    const casesView = paneTree(ELS, snap, { tab: 1, selected: null, editing: null }, act);
    const approvalsView = paneTree(ELS, snap, { tab: 2, selected: null, editing: null }, act);
    assert.equal(JSON.stringify(casesView).includes(CASE_ID), true);
    assert.equal(JSON.stringify(approvalsView).includes(HASH8), true);
    assert.notEqual(
      findNode(approvalsView, (n) => isButton(n) && /Approvals \(1\)/.test(n.props?.label ?? "")),
      null,
    );
    await findNode(approvalsView, byKey("tab-1")).props.onPress();
    assert.equal(state.get("tab"), 1);
    // The approvals tab does not draw case rows.
    assert.equal(findNode(approvalsView, byKey(`case-${CASE_ID}`)), null);
  });

  test("the selected case draws the strip and offer bar", async () => {
    const plan = "currency: USD\ntarget: 900\nfacts:\n- 1100\n- 1000\noptions:\n- {kind: price, value: 1200}\n";
    const files = heldFiles({ [`${DIR}/plan.yaml`]: plan });
    const { $ } = fakeDollar({ files, dirs: heldDirs(), held: heldOpt() });
    const snap = await R.scanCases($);
    assert.deepEqual(snap.cases[0].offer, { start: 1100, offer: 1000, target: 900, currency: "USD" });
    const tree = paneTree(ELS, snap, { tab: 1, selected: CASE_ID, editing: null }, R.paneActions($, snap));
    const flat = JSON.stringify(tree);
    assert.match(flat, /\[Sent\]/);
    assert.match(flat, /start \$1100 · offer \$1000 · target \$900/);
  });

  test("gate rows show pass, hold, and block", () => {
    const props = (output, over = {}) => ({
      tool: "Bash", tool_use_id: "tu1",
      input: { command: `python3 ${BT} gate ${CASE_ID} --draft ${DIR}/draft.yaml` },
      isRunning: false, isErrored: false, isInterrupted: false, output, ...over,
    });
    const out = (stdout) => ({ stdout, stderr: "" });
    assert.equal(gateRow(props(out('{"result":"pass","reasons":[]}')))?.text, "✓ Gate pass");
    assert.match(
      gateRow(props(out('{"result":"block","reasons":["outside your limits"]}'))).text,
      /^✗ Gate block: outside your limits/,
    );
    assert.equal(
      gateRow(props(out(`{"result":"needs_approval","reasons":["x"],"hash":"${HASH}"}`)))?.text,
      "● Held for you",
    );
    // A non-gate row and a still-running row draw nothing.
    assert.equal(gateRow(props(null, { input: { command: "ls" } })), null);
    assert.equal(gateRow(props(null, { isRunning: true })), null);
  });

  test("band text counts held drafts and draws Review", () => {
    const el = { Box: "Box", Text: "Text", Button: "Button" };
    const tree = bandTree(el, { held: 1, pending: 0, repliers: ["Comcast"] }, () => {});
    assert.match(JSON.stringify(tree), /Comcast replied, 1 draft waiting/);
    assert.equal(findNode(tree, byKey("review")).props.hotkey, "2");
    assert.equal(bandTree(el, { held: 0, pending: 0, repliers: [] }, () => {}), null);
  });
});
