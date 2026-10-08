// Approval-surface security tests: the held tuple display and the
// edit-path draft.yaml serialization. Run: node --test 'mod/*.test.js'

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as A from "./lib/approvals.js";
import { parseFlatYaml } from "./lib/parse.js";
import { paneTree } from "./ui/pane.js";
import * as R from "./register.js";
import { CASE_ID, DIR, fakeDollar } from "./testkit.js";
import { ELS, REC, HASH, heldFiles, heldDirs, findNode, byKey } from "./heldkit.js";

describe("exact approval amounts", () => {
  test("moneyExact keeps cents; money() still rounds for savings", () => {
    assert.equal(A.moneyExact("USD", 14.65), "$14.65");
    assert.equal(A.moneyExact("USD", 1200), "$1200.00");
    assert.equal(A.moneyExact("EUR", 200), "EUR 200.00");
    assert.equal(A.money("USD", 14.65), "$15");
  });

  test("tupleText joins action, exact offer and period", () => {
    assert.equal(
      A.tupleText({ action: "send", offer: 14.65, period: "month", currency: "USD" }),
      "send · $14.65/month",
    );
    // A one-time offer is not a rate: "once" must be explicit so the
    // bare amount never reads as recurring.
    assert.equal(
      A.tupleText({ action: "send", offer: 50, period: "once", currency: "USD" }),
      "send · $50.00 once",
    );
    assert.equal(A.tupleText(REC), "cancel");
    assert.equal(A.tupleText({ action: "send", offer: null }), "send");
    assert.equal(A.tupleText({}), "");
  });

  test("the approval card shows the tuple line", async () => {
    const { $ } = fakeDollar({
      files: heldFiles(),
      dirs: heldDirs(),
      held: { [CASE_ID]: [{ ...REC, action: "send", offer: 14.65, period: "month" }] },
    });
    const snap = await R.scanCases($);
    const tree = paneTree(
      ELS, snap, { tab: 2, selected: null, editing: null },
      R.paneActions($, snap));
    assert.equal(
      findNode(tree, byKey(`held-u-${HASH.slice(0, 8)}`))?.children?.[0],
      undefined,
    );
    // The tuple text sits somewhere in the card's own Text nodes.
    assert.match(JSON.stringify(tree), /send · \$14\.65\/month/);
  });
});

describe("edit-path draft serialization", () => {
  const write = (held, text) => parseFlatYaml(A.draftYaml(held, text));

  test("the send tuple comes from the held record, never draft.yaml", () => {
    // A stale card must not borrow a newer draft's fields: only the
    // held tuple lands, and claims never serialize as {}.
    const out = write(
      { action: "send", offer: 14.65, period: "month", currency: "USD" },
      "edited text");
    assert.equal(out.action, "send");
    assert.equal(out.offer, 14.65);
    assert.equal(out.period, "month");
    const raw = A.draftYaml(REC, "x");
    assert.equal(raw.includes("claims"), false);
    assert.equal(raw.includes("{}"), false);
  });

  test("a held record missing fields writes no invented keys", () => {
    const raw = A.draftYaml({ rendered: "x" }, "hi");
    assert.equal(raw.includes("action"), false);
    assert.equal(raw.includes("offer"), false);
    assert.equal(raw.includes("period"), false);
  });

  test("template text round-trips byte-exact", () => {
    const held = { action: "send", offer: 1200, period: "year" };
    for (const text of [
      "plain one-line",
      " first line leads with a space",
      "line one\n\nline three after a blank",
      "trailing newline\n",
      "two trailing\n\n",
      "a # hash and 'quotes' stay",
      "counterparty said {quote:1} here",
      "ends mid-",
      "",
    ]) {
      assert.equal(write(held, text).template, text, JSON.stringify(text));
    }
  });
});
