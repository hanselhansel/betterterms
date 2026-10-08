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
  DIR, DRAFT, GATE, THREAD,
  caseDirs, caseFiles, fakeDollar, fakeOn, fired,
} from "./testkit.js";

const HERE = dirname(fileURLToPath(import.meta.url));

describe("register", () => {
  test("hooks.json names ../register.js and the file exists", () => {
    const hooks = JSON.parse(readFileSync(join(HERE, "hooks/hooks.json"), "utf8"));
    assert.deepEqual(hooks.modules, ["../register.js"]);
    // Claude resolves module paths relative to hooks/hooks.json.
    readFileSync(join(HERE, "hooks", hooks.modules[0]), "utf8");
  });

  test("the mod registers no tool.call or prompt.submit hook", () => {
    // The mod is a cockpit only (decision 0020): outgoing calls and
    // user prompts pass straight through.
    fakeDollar();
    const on = fakeOn();
    register(on.on);
    assert.equal(on.hooks.some((h) => h.event === "tool.call"), false);
    assert.equal(on.hooks.some((h) => h.event === "prompt.submit"), false);
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
