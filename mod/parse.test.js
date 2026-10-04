// File-format reader tests. Run: node --test mod/

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { parseFlatYaml, parseThread, parseLedger } from "./lib/parse.js";
import { BRIEF, DRAFT, THREAD, LEDGER } from "./testkit.js";

describe("parseFlatYaml", () => {
  test("reads scalars, lists, null and a nested mapping", () => {
    const brief = parseFlatYaml(BRIEF);
    assert.equal(brief.pack, "bills");
    assert.equal(brief.mode, "act");
    assert.equal(brief.autonomy, 2);
    assert.equal(brief.deadline, null);
    assert.deepEqual(brief.goals, ["lower the bill"]);
    assert.deepEqual(brief.priorities, ["price", "terms"]);
    assert.deepEqual(brief.never_disclose, ["acct-7788"]);
    assert.equal(brief.ranking_check.passed, true);
  });

  test("reads a PyYAML single-quoted multiline scalar", () => {
    const draft = parseFlatYaml(DRAFT);
    assert.equal(draft.action, "send");
    assert.equal(draft.offer, 1000);
    assert.equal(draft.period, "year");
    assert.equal(
      draft.template,
      "I can pay {offer} for this plan.\nIf that works, say the word and I will set it up.",
    );
    assert.deepEqual(draft.claims, ["f1"]);
  });

  test("reads literal blocks, flow lists and quoted scalars", () => {
    const v = parseFlatYaml(
      "a: |\n  one\n  two\nb: [x, y]\nc: 'it''s'\nd: \"say \\\"hi\\\"\"\ne: 2.5\n",
    );
    assert.equal(v.a, "one\ntwo\n");
    assert.deepEqual(v.b, ["x", "y"]);
    assert.equal(v.c, "it's");
    assert.equal(v.d, 'say "hi"');
    assert.equal(v.e, 2.5);
  });

  test("garbage in, empty map out, never throws", () => {
    assert.deepEqual(parseFlatYaml(""), {});
    assert.deepEqual(parseFlatYaml("::::\n  - [broken"), {});
  });
});

describe("parseThread", () => {
  test("reads entries with direction, stamp, approval and snippet", () => {
    const entries = parseThread(THREAD);
    assert.equal(entries.length, 2);
    assert.equal(entries[0].dir, "in");
    assert.equal(entries[0].approved, false);
    assert.equal(entries[0].snippet, "We can do $1,100 a year.");
    assert.equal(entries[1].dir, "out");
    assert.equal(entries[1].approved, true);
  });

  test("empty thread has no entries", () => {
    assert.deepEqual(parseThread("# thread x\n"), []);
    assert.deepEqual(parseThread(""), []);
  });
});

describe("parseLedger", () => {
  test("collects closed case ids and yearly savings per currency", () => {
    const { closed, saved } = parseLedger(LEDGER);
    assert.equal(closed.has("bills-20260901-aaaa"), true);
    assert.equal(closed.has("offer-20260902-bbbb"), true);
    assert.deepEqual(saved, { USD: 1440 });
  });

  test("sums stay per currency; a missing currency is USD", () => {
    const { saved } = parseLedger([
      '{"case_id":"a-20260101-aaaa","saved_per_year":240,"currency":"EUR"}',
      '{"case_id":"b-20260101-bbbb","saved_per_year":1200}',
    ].join("\n"));
    assert.deepEqual(saved, { EUR: 240, USD: 1200 });
  });
});
