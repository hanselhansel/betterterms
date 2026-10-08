// Shared held-draft fixtures for the approval test files. Not a test
// file itself: `node --test` only picks up *.test.js.

import * as R from "./register.js";
import { paneTree } from "./ui/pane.js";
import {
  CASE_ID, DIR, DRAFT, RENDERED,
  caseDirs, caseFiles, heldHash,
} from "./testkit.js";

// The held record's send tuple; the hash the fake CLI reports is the
// tuple hash, exactly what bt.py computes. `inbound` is the reviewed
// context digest a real record always carries.
export const REC = {
  action: "cancel", offer: null, period: "once", currency: "USD",
  rendered: RENDERED,
  inbound: "0".repeat(64),
  reasons: ["action 'cancel' requires --approved"],
  held_at: "2026-10-04T12:00:00+00:00",
};
export const HASH = heldHash(REC);
export const HASH8 = HASH.slice(0, 8);
export const GATE_HELD_JSON = JSON.stringify({
  result: "needs_approval",
  reasons: ["action 'cancel' requires --approved"],
  rendered: RENDERED,
  hash: HASH,
});
export const ELS = { Box: "Box", Text: "Text", Button: "Button", Input: "Input" };

export const heldFiles = (extra = {}) => caseFiles({
  [`${DIR}/draft.yaml`]: DRAFT,
  // gate.json carries the held hash: the pane's approve refuses any
  // held hash that is not the case's current gate.json hash.
  [`${DIR}/gate.json`]: GATE_HELD_JSON,
  ...extra,
});
export const heldDirs = () => caseDirs({
  [`${DIR}/held`]: [],
});
export const heldOpt = () => ({ [CASE_ID]: [REC] });
// The Approvals-tab tree for a one-held-draft snapshot.
export const approvalsCard = async ($) => {
  const snap = await R.scanCases($);
  return paneTree(ELS, snap, { tab: 2, selected: null, editing: null }, R.paneActions($, snap));
};

// Depth-first walk of an h() tree for the first node whose props or
// text match. The node shape is {tag, props, children}.
export function findNode(tree, pred) {
  if (!tree || typeof tree !== "object") return null;
  if (pred(tree)) return tree;
  for (const ch of tree.children ?? []) {
    const hit = findNode(ch, pred);
    if (hit) return hit;
  }
  return null;
}
export const isButton = (n) => n.tag === "Button";
export const byKey = (k) => (n) => n.props?.key === k;
