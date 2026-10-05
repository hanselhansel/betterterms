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
  ELS, REC, HASH, HASH8, GATE_HELD_JSON,
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

  test("approve writes the marker and submits the gate prompt", async () => {
    const { $, calls, state } = held$();
    await approvePress($);
    // No $.state approvals: the marker file held approve writes is
    // the only consent record, and the gate spends it.
    assert.equal(state.get("approvals"), undefined);
    assert.equal(calls.submit.length, 1);
    assert.match(calls.submit[0], new RegExp(`approved draft ${HASH8} for ${CASE_ID}`));
    assert.match(calls.submit[0], /bt\.py gate \S+ --approved/);
    assert.match(calls.submit[0], /verbatim as its own argument/);
  });

  test("the marker the press armed spends exactly once", async () => {
    // The press runs `held approve`, which writes the marker; the
    // agent's own `gate --approved` run then spends it, and a second
    // run holds the draft again. That hash-bound one use is the send
    // enforcement in every mode, mod included.
    const files = heldFiles();
    const route = btRoute(
      { held: heldOpt(), gate: JSON.parse(GATE_HELD_JSON) }, files);
    const { $ } = fakeDollar({ files, dirs: heldDirs(), held: heldOpt(), run: route });
    await approvePress($);
    const gate = ["python3", BT, "gate", CASE_ID, "--draft", `${DIR}/draft.yaml`, "--approved"];
    const first = route(gate);
    assert.equal(first.exitCode, 0, first.stdout);
    assert.match(first.stdout, /"result":\s*"pass"/);
    const second = route(gate);
    assert.notEqual(second.exitCode, 0, "the marker is one use");
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

  test("the mod registers no tool.call or prompt.submit hook", () => {
    // The send check left the release (decision 0020): outgoing tool
    // calls and prompts pass through uninspected. The gate's
    // --approved marker is the only send enforcement.
    const on = fakeOn();
    register(on.on);
    assert.equal(on.hooks.some((h) => h.event === "tool.call"), false);
    assert.equal(on.hooks.some((h) => h.event === "prompt.submit"), false);
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
  test("saving an edit drops the held record, writes draft.yaml, re-gates", async () => {
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
    // The old held record is dropped quietly before the re-gate: the
    // card answered for the old text, so no approval for it may live
    // on under a hash the edited draft can no longer match.
    const dropIdx = calls.run.findIndex((r) => r.argv[3] === "drop");
    const gateIdx = calls.run.findIndex((r) => r.argv[2] === "gate");
    assert.ok(dropIdx !== -1, "held drop did not run");
    assert.ok(gateIdx !== -1, "the re-gate did not run");
    assert.ok(dropIdx < gateIdx, "held drop must run before the re-gate");
    assert.deepEqual(calls.run[dropIdx].argv, ["python3", BT, "held", "drop", CASE_ID, HASH8]);
    const wrote = calls.write.find((w) => w.path === `${DIR}/draft.yaml`);
    assert.ok(wrote);
    assert.match(wrote.text, /template: \|-/);
    assert.match(wrote.text, /I can pay \$1,200 a year/);
    assert.match(wrote.text, /action: send/);
  });

  test("edit then press a approves the new text only; the old card is gone", async () => {
    const EDITED = "I can pay $1,200 a year for this plan.";
    const NEW = { ...REC, rendered: EDITED };
    const NEW_HASH = heldHash(NEW);
    const NEW8 = NEW_HASH.slice(0, 8);
    const files = heldFiles();
    const opts = {
      held: heldOpt(),
      // The fake gate answers for whatever draft.yaml now holds and
      // writes the new held record, like the real `bt.py gate`.
      gate: () => {
        const edited = String(files[`${DIR}/draft.yaml`]).includes("1,200");
        if (edited) {
          opts.held[CASE_ID] = [NEW];
          files[`${DIR}/held/${NEW_HASH}.yaml`] = JSON.stringify(NEW);
        }
        return {
          result: "needs_approval",
          reasons: ["action 'cancel' requires --approved"],
          rendered: edited ? EDITED : RENDERED,
          hash: edited ? NEW_HASH : HASH,
        };
      },
    };
    const { $, calls, state } = fakeDollar({ files, dirs: heldDirs(), ...opts });
    const snap1 = await R.scanCases($);
    const tree1 = paneTree(
      ELS, snap1, { tab: 2, selected: null, editing: HASH }, R.paneActions($, snap1));
    await findNode(tree1, (n) => n.tag === "Input").props.onSubmit(EDITED);
    // The old held record was dropped before the re-gate.
    assert.equal(calls.run.some((r) => r.argv[3] === "drop"), true);
    const snap2 = await R.scanCases($);
    const tree2 = paneTree(
      ELS, snap2, { tab: 2, selected: null, editing: null }, R.paneActions($, snap2));
    // The old card is gone; the edited text sits under its new hash.
    assert.equal(findNode(tree2, byKey(`approve-${HASH8}`)), null);
    const card = findNode(tree2, byKey(`approve-${NEW8}`));
    assert.ok(card, "no card for the edited draft");
    await card.props.onPress();
    assert.equal(
      calls.run.some(
        (r) => r.argv.join(" ") === `python3 ${BT} held approve ${CASE_ID} ${NEW8}`),
      true,
    );
    // The marker file is the consent record; no $.state approvals.
    assert.equal(`${DIR}/held/${NEW_HASH}.approved` in files, true);
    assert.equal(`${DIR}/held/${HASH}.approved` in files, false);
    assert.equal(state.get("approvals"), undefined);
    assert.equal(calls.submit.length, 1);
  });
});

describe("stale held drafts", () => {
  // gate.json carries the hash of the draft the last gate verdict
  // held; a held record whose hash does not match it is stale (the
  // draft was edited, the card belongs to old text) and must never
  // approve.
  const staleFiles = () => heldFiles({
    [`${DIR}/gate.json`]: JSON.stringify({
      result: "needs_approval",
      reasons: ["action 'cancel' requires --approved"],
      rendered: "a different held text",
      hash: heldHash({ ...REC, rendered: "a different held text" }),
    }),
  });

  test("a press refuses a held hash that is not the gate.json hash", async () => {
    const { $, calls, state } = fakeDollar({
      files: staleFiles(), dirs: heldDirs(), held: heldOpt(),
    });
    const snap = await R.scanCases($);
    const tree = paneTree(
      ELS, snap, { tab: 2, selected: null, editing: null }, R.paneActions($, snap));
    await findNode(tree, byKey(`approve-${HASH8}`)).props.onPress();
    assert.equal(calls.run.every((r) => r.argv[3] !== "approve"), true);
    assert.equal(calls.submit.length, 0);
    assert.equal(state.size, 0);
    assert.match(calls.toast.join("\n"), /not the current held draft/);
  });
});
