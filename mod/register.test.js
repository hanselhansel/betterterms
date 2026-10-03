// Hook-wiring tests for register.js. Run: node --test mod/
// A fake engine stands in for `$` and `on`; the only disk read is
// hooks.json, which pins the manifest contract Claude resolves at load.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { register } from "./register.js";
import {
  BT, BRIEF, CASE_ID, DIR, DRAFT, GATE, GATE_NEEDS_APPROVAL, RENDERED,
  THREAD, caseDirs, caseFiles, fakeDollar, fakeOn, fired,
} from "./testkit.js";

const HERE = dirname(fileURLToPath(import.meta.url));

describe("register", () => {
  test("hooks.json names ../register.js and the file exists", () => {
    const hooks = JSON.parse(readFileSync(join(HERE, "hooks/hooks.json"), "utf8"));
    assert.deepEqual(hooks.modules, ["../register.js"]);
    // Claude resolves module paths relative to hooks/hooks.json.
    readFileSync(join(HERE, "hooks", hooks.modules[0]), "utf8");
  });

  test("a send carrying the rendered text is denied when the gate blocks", async () => {
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT, [`${DIR}/gate.json`]: GATE });
    const { $, calls } = fakeDollar({
      files, dirs: caseDirs(),
      gate: { exitCode: 1, stdout: '{"result":"block","reasons":["floor disclosed in draft text"]}', stderr: "" },
    });
    const on = fakeOn();
    register(on.on);
    const { next, calls: went } = fired();
    const out = await on.get("tool.call")($, {
      tool: "Bash", tool_use_id: "t1", command: `mail x <<EOF\n${RENDERED}\nEOF`,
    }, next);
    assert.equal(went.length, 0);
    assert.match(out.deny, /betterterms/);
    assert.match(out.deny, /floor/);
    assert.equal(calls.run.length, 1);
    assert.deepEqual(calls.run[0].argv, [
      "python3", BT, "gate", CASE_ID, "--draft", `${DIR}/draft.yaml`,
    ]);
  });

  test("unrelated tool calls pass through untouched", async () => {
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT, [`${DIR}/gate.json`]: GATE });
    const { $, calls } = fakeDollar({ files, dirs: caseDirs() });
    const on = fakeOn();
    register(on.on);
    const { next, marker } = fired();
    const out = await on.get("tool.call")($, { tool: "Bash", tool_use_id: "t1", command: "ls -la" }, next);
    assert.equal(out, marker);
    assert.equal(calls.run.length, 0);
  });

  test("writes into the case dir are bookkeeping, not sends", async () => {
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT, [`${DIR}/gate.json`]: GATE });
    const { $, calls } = fakeDollar({ files, dirs: caseDirs() });
    const on = fakeOn();
    register(on.on);
    const { next, marker } = fired();
    // gate.json holds the rendered text, so a bookkeeping write of the
    // verdict itself would trip the matcher without the case-dir check.
    const out = await on.get("tool.call")($, {
      tool: "Write", tool_use_id: "t2", file_path: `${DIR}/gate.json`, content: GATE,
    }, next);
    assert.equal(out, marker);
    assert.equal(calls.run.length, 0);
  });

  test("autonomy 2: a passing gate still asks the user first", async () => {
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT, [`${DIR}/gate.json`]: GATE });
    const { $, calls } = fakeDollar({ files, dirs: caseDirs(), answer: "Send" });
    const on = fakeOn();
    register(on.on);
    const { next, calls: went, marker } = fired();
    const out = await on.get("tool.call")($, {
      tool: "Bash", tool_use_id: "t3", command: `send ${RENDERED}`,
    }, next);
    assert.equal(calls.ask.length, 1);
    assert.equal(out, marker);
    assert.equal(went.length, 1);
  });

  test("a refused approval denies the send", async () => {
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT, [`${DIR}/gate.json`]: GATE });
    const { $, calls } = fakeDollar({ files, dirs: caseDirs(), answer: "Hold" });
    const on = fakeOn();
    register(on.on);
    const { next, calls: went } = fired();
    const out = await on.get("tool.call")($, {
      tool: "Bash", tool_use_id: "t4", command: `send ${RENDERED}`,
    }, next);
    assert.equal(went.length, 0);
    assert.match(out.deny, /betterterms/);
    assert.equal(calls.ask.length, 1);
  });

  test("irreversible at high autonomy: ask, then re-gate with --approved", async () => {
    const cancelDraft = DRAFT.replace("action: send", "action: cancel");
    const aut4 = BRIEF.replace("autonomy: 2", "autonomy: 4");
    const files = caseFiles({
      [`${DIR}/draft.yaml`]: cancelDraft,
      [`${DIR}/brief.yaml`]: aut4,
      [`${DIR}/gate.json`]: GATE_NEEDS_APPROVAL,
    });
    const gates = [
      { exitCode: 3, stdout: '{"result":"needs_approval","reasons":["action \'cancel\' requires --approved"]}', stderr: "" },
      { exitCode: 0, stdout: '{"result":"pass","reasons":[]}', stderr: "" },
    ];
    const { $, calls } = fakeDollar({ files, dirs: caseDirs(), answer: "Send" });
    let i = 0;
    $.process.run = async (argv) => { calls.run.push({ argv }); return gates[Math.min(i++, gates.length - 1)]; };
    const on = fakeOn();
    register(on.on);
    const { next, marker } = fired();
    const out = await on.get("tool.call")($, {
      tool: "Bash", tool_use_id: "t5", command: `cancel: ${RENDERED}`,
    }, next);
    assert.equal(out, marker);
    assert.equal(calls.run.length, 2);
    assert.equal(calls.run[1].argv.includes("--approved"), true);
  });

  test("session.start registers the command, opens the pane, starts the poll", async () => {
    const { $, calls } = fakeDollar({ files: caseFiles(), dirs: caseDirs() });
    const on = fakeOn();
    register(on.on);
    const { next, marker } = fired();
    const out = await on.get("session.start")($, {}, next);
    assert.equal(out, marker);
    assert.equal(calls.register.some((s) => s.name === "betterterms-cases"), true);
    assert.equal(calls.open.some((r) => r.id === "betterterms"), true);
    assert.equal(calls.every.length, 1);
  });

  test("the poll toasts once per new inbound entry", async () => {
    const files = caseFiles();
    const { $, calls } = fakeDollar({ files, dirs: caseDirs() });
    const on = fakeOn();
    register(on.on);
    const { next } = fired();
    await on.get("session.start")($, {}, next);
    assert.equal(calls.toast.length, 0);
    files[`${DIR}/thread.md`] = THREAD + "## in 2026-10-03T16:00:00+00:00 approved_by_user: no\nCounter offer: $950.\n";
    await calls.every[0].fn();
    assert.equal(calls.toast.length, 1);
    assert.match(calls.toast[0], /bills-20261003-a1b2/);
    await calls.every[0].fn();
    assert.equal(calls.toast.length, 1);
  });

  test("AbovePrompt counts gated unsent drafts, defers when none", async () => {
    const files = caseFiles({ [`${DIR}/draft.yaml`]: DRAFT, [`${DIR}/gate.json`]: GATE });
    const dirs = caseDirs();
    const stats = {
      [`${DIR}/draft.yaml`]: { mtimeMs: 10 },
      [`${DIR}/gate.json`]: { mtimeMs: 11 },
      [`${DIR}/thread.md`]: { mtimeMs: 1 },
    };
    const { $ } = fakeDollar({ files, dirs, stats });
    const on = fakeOn();
    register(on.on);
    const band = on.get("ui.render", (h) => h.matcher?.component === "AbovePrompt");
    const { next, marker } = fired({ view: "default" });
    const out = await band($, { props: { hasSurvey: false } }, next);
    assert.notEqual(out, marker);
    const quiet = fakeDollar({ files: caseFiles(), dirs });
    const out2 = await band(quiet.$, { props: { hasSurvey: false } }, fired({ view: "default" }).next);
    assert.equal(out2.view, "default");
  });

  test("Pane renders a row per case", async () => {
    const { $ } = fakeDollar({ files: caseFiles(), dirs: caseDirs() });
    const on = fakeOn();
    register(on.on);
    const pane = on.get("ui.render", (h) => h.matcher?.component === "Pane");
    const tree = await pane($, { props: {}, viewport: { rows: 24 } });
    const flat = JSON.stringify(tree);
    assert.match(flat, /bills-20261003-a1b2/);
    assert.match(flat, /waiting/);
  });
});
