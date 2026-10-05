// The user-facing wordings in lib/approvals.js and the thread.md
// markers: hash8 prefixes, deny/approve notes, the status line with
// its per-currency and one-time figures. Split from
// approvals.test.js under the 400-line cap.
// Run: node --test mod/

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as C from "./lib/cases.js";
import * as A from "./lib/approvals.js";
import { CASE_ID, THREAD } from "./testkit.js";
import { HASH, HASH8 } from "./heldkit.js";

describe("lib/approvals helpers", () => {
  test("hash8 takes the first 8 hex chars", () => {
    assert.equal(A.hash8(HASH), HASH8);
    assert.equal(A.hash8("abc"), "abc");
    assert.equal(A.hash8(null), null);
  });

  test("approvePromptText sends the agent through gate --approved", () => {
    // The press arms the marker; the prompt tells the agent to run
    // `bt.py gate <case> --approved` once and send the rendered text
    // it returns verbatim as its own argument (decision 0020).
    const text = A.approvePromptText(HASH, CASE_ID);
    assert.match(text, new RegExp(`approved draft ${HASH8} for ${CASE_ID}`));
    assert.match(text, new RegExp(`bt\\.py gate ${CASE_ID} --approved`));
    assert.match(text, /verbatim as its own argument/);
    assert.match(text, /once/);
    assert.doesNotMatch(text, /send guard|send check/i);
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

  test("statusText shows one-time savings as once, not per year", () => {
    assert.equal(
      A.statusText(1, { USD: 1440 }, { USD: 100 }),
      "bt: 1 case · $1440/yr saved · $100 once",
    );
    assert.equal(
      A.statusText(1, {}, { USD: 100, EUR: 50 }),
      "bt: 1 case · $0/yr saved · $100 once · EUR 50 once",
    );
    // No once sums: the line keeps its old shape exactly.
    assert.equal(
      A.statusText(1, { USD: 1440 }, {}),
      "bt: 1 case · $1440/yr saved",
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
