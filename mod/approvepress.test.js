// Approve/reject press, edit-flow and status-line tests for the
// betterterms mod. Run: node --test mod/ (split out of
// approvals.test.js to keep both files under the 400-line cap).

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { paneTree } from "./ui/pane.js";
import { register } from "./register.js";
import * as R from "./register.js";
import {
  BT, CASE_ID, DIR, RENDERED,
  fakeDollar, fakeOn, fired, heldHash, btRoute,
} from "./testkit.js";
import {
  ELS, REC, HASH, HASH8,
  heldFiles, heldDirs, heldOpt, approvalsCard,
  findNode, byKey,
} from "./heldkit.js";

describe("approve press", () => {
  const approvePress = async ($) =>
    findNode(await approvalsCard($), byKey(`approve-${HASH8}`)).props.onPress();
  const held$ = (opts = {}) => fakeDollar({
    files: heldFiles(), dirs: heldDirs(), held: heldOpt(), ...opts,
  });

  test("approve runs held approve with hash8", async () => {
    const { $, calls } = held$();
    await approvePress($);
    const approveRun = calls.run.find((r) => r.argv[3] === "approve");
    assert.deepEqual(approveRun.argv, ["python3", BT, "held", "approve", CASE_ID, HASH8]);
  });

  test("approval stores full hash and submits prompt", async () => {
    const { $, calls, state } = held$();
    await approvePress($);
    assert.equal(state.get("approvals")?.[HASH], true);
    assert.equal(calls.submit.length, 1);
    assert.match(calls.submit[0], new RegExp(`approved draft ${HASH8} for ${CASE_ID}`));
  });

  test("approval failure does not submit", async () => {
    const files = heldFiles();
    // Build the route eagerly: its construction materializes the
    // held/*.yaml files the scan's fingerprint needs to see.
    const base = btRoute({ held: heldOpt() }, files);
    const { $, calls, state } = fakeDollar({
      files, dirs: heldDirs(), held: heldOpt(),
      run: (argv) => argv[3] === "approve"
        ? { exitCode: 2, stdout: `{"error":"no held draft matching ${HASH8}"}`, stderr: "" }
        : base(argv),
    });
    await approvePress($);
    assert.equal(calls.submit.length, 0);
    assert.equal(state.size, 0);
    assert.match(calls.toast.join("\n"), /approve failed/);
  });

  test("reject runs held reject with hash8", async () => {
    const { $, calls } = held$();
    await findNode(await approvalsCard($), byKey(`reject-${HASH8}`)).props.onPress();
    const rejectRun = calls.run.find((r) => r.argv[3] === "reject");
    assert.deepEqual(rejectRun.argv, ["python3", BT, "held", "reject", CASE_ID, HASH8]);
  });

  test("a/e/r bind on the top card only when several drafts wait", async () => {
    const REC2 = {
      action: "send", offer: 900, period: "year", currency: "USD",
      rendered: "I can pay $900 a year if that closes this out.",
      reasons: ["offer exceeds autonomy"], held_at: "2026-10-04T13:00:00+00:00",
    };
    const HASH2 = heldHash(REC2);
    const { $ } = fakeDollar({
      files: heldFiles(), dirs: heldDirs(), held: { [CASE_ID]: [REC, REC2] },
    });
    const tree = await approvalsCard($);
    // The oldest (first listed) card takes the keys; the rest need a press.
    assert.equal(findNode(tree, byKey(`approve-${HASH8}`)).props.hotkey, "a");
    assert.equal(findNode(tree, byKey(`edit-open-${HASH8}`)).props.hotkey, "e");
    assert.equal(findNode(tree, byKey(`reject-${HASH8}`)).props.hotkey, "r");
    assert.equal(findNode(tree, byKey(`approve-${HASH2.slice(0, 8)}`)).props.hotkey, undefined);
    assert.match(JSON.stringify(tree), /top card/);
  });
});

describe("session.start status line", () => {
  test("status text equals bt: <n> cases · $<saved>/yr saved", async () => {
    const { $, calls } = fakeDollar({
      files: heldFiles(), dirs: heldDirs(), held: heldOpt(),
    });
    const on = fakeOn();
    register(on.on);
    await on.get("session.start")($, { isInteractive: true }, fired().next);
    assert.equal(calls.status[calls.status.length - 1], "bt: 1 case · $1440/yr saved");
  });
});

describe("edit flow", () => {
  test("saving an edit writes draft.yaml and re-runs the gate", async () => {
    const { $, calls } = fakeDollar({
      files: heldFiles(), dirs: heldDirs(), held: heldOpt(),
      gate: {
        result: "needs_approval",
        reasons: ["action 'cancel' requires --approved"],
        rendered: RENDERED, hash: HASH,
      },
    });
    const snap = await R.scanCases($);
    const tree = paneTree(ELS, snap, { tab: 2, selected: null, editing: HASH }, R.paneActions($, snap));
    const input = findNode(tree, (n) => n.tag === "Input");
    assert.equal(input.props.value, RENDERED);
    await input.props.onSubmit("I can pay $1,200 a year for this plan.");
    const wrote = calls.write.find((w) => w.path === `${DIR}/draft.yaml`);
    assert.ok(wrote);
    assert.match(wrote.text, /template: \|-/);
    assert.match(wrote.text, /I can pay \$1,200 a year/);
    assert.match(wrote.text, /action: send/);
    assert.equal(calls.run.some((r) => r.argv.includes("gate")), true);
  });
});
