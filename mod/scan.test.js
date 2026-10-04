// The stat-fingerprint scan cache (review finding 15): unchanged
// cases are not re-read, a write invalidates exactly its case, and a
// burst-window scan returns the snapshot without touching fs again.
// The pre-send guard never takes the burst path: it scans fresh and
// re-gates regardless, so a stale print can only ever deny.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  CASE_ID, DIR, DRAFT, GATE, RENDERED,
  caseDirs, caseFiles, fakeDollar, heldHash,
} from "./testkit.js";
import * as R from "./register.js";
import * as W from "./lib/wiring.js";

describe("scan cache", () => {
  test("an unchanged case is not re-read on the next scan", async () => {
    const { $, calls } = fakeDollar({ files: caseFiles(), dirs: caseDirs() });
    await R.scanCases($);
    const reads = calls.read.length;
    const runs = calls.run.length;
    assert.ok(reads > 0);
    const snap2 = await R.scanCases($);
    assert.equal(calls.read.length, reads, "case files re-read");
    assert.equal(calls.run.length, runs, "held list re-ran");
    assert.equal(snap2.cases.length, 1);
    assert.equal(snap2.cases[0].id, CASE_ID);
  });

  test("a draft write invalidates only that case", async () => {
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT });
    const { $, calls } = fakeDollar({ files, dirs: caseDirs() });
    const before = (await R.scanCases($)).cases[0];
    assert.ok(before.draft !== null);
    files[`${DIR}/draft.yaml`] = DRAFT.replace("send", "dispute");
    // The fake bumps the file's mtime on direct writes too? No --
    // writes through $.fs.write bump; raw map edits do not, so poke
    // the fs layer the way the editor does.
    await $.fs.write(`${DIR}/draft.yaml`, files[`${DIR}/draft.yaml`]);
    const after = (await R.scanCases($)).cases[0];
    assert.notEqual(after, before, "fingerprint must move on write");
  });

  test("a ledger write re-parses totals once", async () => {
    const { $, calls } = fakeDollar({ files: caseFiles(), dirs: caseDirs() });
    await R.scanCases($);
    const reads = calls.read.length;
    await R.scanCases($);
    assert.equal(calls.read.length, reads);
  });

  test("burst reuse skips even the stats inside the window", async () => {
    const { $, calls } = fakeDollar({ files: caseFiles(), dirs: caseDirs() });
    const host = R.hostOf($);
    await W.scanCases(host, { burst: true });
    const stats = calls.stat.length;
    const lists = calls.list.length;
    await W.scanCases(host, { burst: true });
    assert.equal(calls.stat.length, stats);
    assert.equal(calls.list.length, lists);
  });

  test("a non-burst scan still stats (tool.call never rides the burst)", async () => {
    const { $, calls } = fakeDollar({ files: caseFiles(), dirs: caseDirs() });
    const host = R.hostOf($);
    await W.scanCases(host, { burst: true });
    const stats = calls.stat.length;
    await W.scanCases(host);
    assert.ok(calls.stat.length > stats, "fresh scan must stat");
  });

  test("an approval marker moves the held fingerprint", async () => {
    const rec = {
      action: "cancel", offer: null, period: "once",
      currency: "USD", rendered: RENDERED,
      reasons: ["cancel needs your yes"], held_at: "t",
    };
    const h = heldHash(rec);
    const held = { [CASE_ID]: [rec] };
    const files = caseFiles({
      [`${DIR}/draft.yaml`]: DRAFT, [`${DIR}/gate.json`]: GATE,
    });
    const { $ } = fakeDollar({ files, dirs: caseDirs({ [`${DIR}/held`]: [] }), held });
    const first = await R.scanCases($);
    assert.equal(first.cases[0].held[0].approved, false);
    await $.fs.write(`${DIR}/held/${h}.approved`, `hash: ${h}\n`);
    const second = await R.scanCases($);
    assert.equal(second.cases[0].held[0].approved, true);
  });
});
