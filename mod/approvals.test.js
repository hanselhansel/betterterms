// Approval-flow and cockpit tests for the betterterms mod.
// Run: node --test mod/
// Pure helpers and the hook wiring are exercised through the fake
// engine in testkit.js; the engine-side cases live in
// approvals.test.tsx for `claude plugin test`.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { bandTree } from "./ui/band.js";
import { paneTree } from "./ui/pane.js";
import { gateRow } from "./ui/rows.js";
import * as R from "./register.js";
import {
  BT, CASE_ID, DIR, RENDERED,
  caseDirs, fakeDollar,
} from "./testkit.js";
import {
  ELS, HASH, HASH8,
  heldFiles, heldDirs, heldOpt,
  findNode, byKey, isButton,
} from "./heldkit.js";


describe("held drafts", () => {
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
