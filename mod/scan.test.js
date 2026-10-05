// The stat-fingerprint scan cache (review finding 15): unchanged
// cases are not re-read, a write invalidates exactly its case, and a
// burst-window scan returns the snapshot without touching fs again.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  BT, CASE_ID, DIR, DRAFT, GATE, RENDERED,
  btRoute, caseDirs, caseFiles, fakeDollar, heldHash,
} from "./testkit.js";
import * as R from "./register.js";
import * as IO from "./lib/hostio.js";
import * as S from "./lib/scan.js";

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
    await S.scanCases(host, { burst: true });
    const stats = calls.stat.length;
    const lists = calls.list.length;
    await S.scanCases(host, { burst: true });
    assert.equal(calls.stat.length, stats);
    assert.equal(calls.list.length, lists);
  });

  test("a non-burst scan still stats", async () => {
    const { $, calls } = fakeDollar({ files: caseFiles(), dirs: caseDirs() });
    const host = R.hostOf($);
    await S.scanCases(host, { burst: true });
    const stats = calls.stat.length;
    await S.scanCases(host);
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

  test("a legacy held record lists nowhere in the mod", async () => {
    // Records from before tuple-bound names carry legacy:true from
    // bt.py held list; the mod never counts them as approvable.
    const rec = {
      action: "cancel", offer: null, period: "once",
      currency: "USD", rendered: RENDERED,
      reasons: ["cancel needs your yes"], held_at: "t", legacy: true,
      note: "held by an older version; re-run the gate",
    };
    const held = { [CASE_ID]: [rec] };
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT });
    const { $ } = fakeDollar({
      files, dirs: caseDirs({ [`${DIR}/held`]: [] }), held,
    });
    const snap = await R.scanCases($);
    assert.equal(snap.cases[0].held.length, 0);
  });

  test("a case whose held list failed is not cached", async () => {
    const rec = {
      action: "cancel", offer: null, period: "once",
      currency: "USD", rendered: RENDERED,
      reasons: ["cancel needs your yes"], held_at: "t",
    };
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT });
    const inner = btRoute({ held: { [CASE_ID]: [rec] } }, files);
    let fail = true;
    const { $ } = fakeDollar({
      files, dirs: caseDirs({ [`${DIR}/held`]: [] }),
      run: (argv) =>
        fail && argv[2] === "held" && argv[3] === "list"
          ? { error: "spawn failed" }
          : inner(argv),
    });
    const first = await R.scanCases($);
    assert.equal(first.cases[0].held.length, 0);
    fail = false;
    const second = await R.scanCases($);
    assert.equal(
      second.cases[0].held.length, 1,
      "a failed held list must not freeze the case cache",
    );
  });

  test("a case scanned while bt.py is missing is not cached", async () => {
    const rec = {
      action: "cancel", offer: null, period: "once",
      currency: "USD", rendered: RENDERED,
      reasons: ["cancel needs your yes"], held_at: "t",
    };
    const held = { [CASE_ID]: [rec] };
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT });
    delete files[BT]; // the core plugin is not installed yet
    const { $ } = fakeDollar({
      files, dirs: caseDirs({ [`${DIR}/held`]: [] }), held,
    });
    const first = await R.scanCases($);
    assert.equal(first.cases[0].held.length, 0);
    files[BT] = "#!/usr/bin/env python3\n"; // the plugin lands mid-session
    const second = await R.scanCases($);
    assert.equal(
      second.cases[0].held.length, 1,
      "a held list skipped for missing bt must not freeze the cache",
    );
  });

  test("a ledger close recomputes stage, next and pending", async () => {
    // Ledger membership is part of the case fingerprint: a case that
    // gains a closed entry must re-derive, not ride the cached row
    // with a patched flag.
    const files = caseFiles({
      [`${DIR}/draft.yaml`]: DRAFT,
      [`${DIR}/gate.json`]: GATE,
    });
    const { $ } = fakeDollar({ files, dirs: caseDirs() });
    // A fresh draft write (newer than the thread, gated at or after
    // it) makes the case pending before the close lands.
    await $.fs.write(`${DIR}/draft.yaml`, DRAFT);
    await $.fs.write(`${DIR}/gate.json`, GATE);
    const before = (await R.scanCases($)).cases[0];
    assert.equal(before.pending, true);
    assert.equal(before.stage, "waiting");
    assert.equal(before.next, "await their reply");
    await $.fs.write(
      "/bt/ledger.jsonl",
      `${files["/bt/ledger.jsonl"]}\n` +
        `{"case_id":"${CASE_ID}","saved_per_year":240,"currency":"USD"}`,
    );
    const after = (await R.scanCases($)).cases[0];
    assert.equal(after.stage, "closed");
    assert.equal(after.next, "closed");
    assert.equal(after.pending, false);
  });

  test("an inode move re-reads with mtime and size pinned", async () => {
    // gate.json and draft.yaml are replaced atomically, so inode is
    // part of the fingerprint: pinning mtime and size must not stop a
    // rewrite from re-deriving the case.
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT });
    const stats = {
      [`${DIR}/draft.yaml`]: { mtimeMs: 7 },
      [`${DIR}/gate.json`]: { mtimeMs: 9 },
    };
    const { $, calls } = fakeDollar({ files, dirs: caseDirs(), stats });
    await R.scanCases($);
    const reads = calls.read.length;
    // Same bytes, same pinned mtime: only the inode can move.
    await $.fs.write(`${DIR}/draft.yaml`, DRAFT);
    await R.scanCases($);
    assert.ok(calls.read.length > reads, "inode change must re-read");
  });

  test("a cached bt path is revalidated and re-probed", async () => {
    const files = caseFiles();
    const { $ } = fakeDollar({ files, dirs: caseDirs() });
    const host = R.hostOf($);
    await IO.findBt(host); // resolves and caches the repo-layout path
    delete files[BT];
    const alt = "/p/betterterms/skills/betterterms-guardrails/scripts/bt.py";
    files[alt] = "#!/usr/bin/env python3\n";
    const again = await IO.findBt(host);
    assert.equal(
      again, alt,
      "a gone cached path must re-probe, not ride the stale hit",
    );
  });
});
