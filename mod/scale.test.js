// Terms-scale layout and terms/savings wiring tests (spec 6.4, 6.5).
// Run: node --test mod/

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import * as S from "./ui/scale.js";
import * as T from "./ui/terms.js";
import * as V from "./ui/savings.js";
import { paneTree } from "./ui/pane.js";
import { register } from "./register.js";
import * as R from "./register.js";
import {
  BT, CASE_ID, DIR, DRAFT,
  caseDirs, caseFiles, fakeDollar, fakeOn, fired,
} from "./testkit.js";

const ELS = { Box: "Box", Text: "Text", Button: "Button", Input: "Input", Select: "Select" };
const ELSC = { ...ELS, Client: "Client" };
const ELSSVG = { ...ELSC, Svg: "Svg" };
const ELSR = { ...ELSC, Raster: "Raster" };

// plan.yaml: target 800, best alternative 850/month, their offer 1000
// after a start of 1100. .floor holds 900.00.
const PLAN = [
  "currency: USD",
  "target: 800",
  "best_alternative:",
  "  amount: 850",
  "  period: month",
  "  note: TMobile quote",
  "facts:",
  "- 1100",
  "- 1000",
  "",
].join("\n");

const termsFiles = (over = {}) => caseFiles({
  [`${DIR}/plan.yaml`]: PLAN,
  [`${DIR}/.floor`]: "900.00\n",
  [`${DIR}/draft.yaml`]: DRAFT,
  ...over,
});

const termsDirs = () => caseDirs();

const LEDGER_TOTAL =
  '{"cases":2,"by_currency":{"USD":1440},"by_pack":{"bills":{"USD":1440}},"warnings":0}';

function findNode(tree, pred) {
  if (!tree || typeof tree !== "object") return null;
  if (pred(tree)) return tree;
  for (const ch of tree.children ?? []) {
    const hit = findNode(ch, pred);
    if (hit) return hit;
  }
  return null;
}
const byKey = (k) => (n) => n.props?.key === k;
const byTag = (t) => (n) => n.tag === t;

// The pane tree as the ui.render hook draws it for these tests: tab 1,
// the terms state and surface carried on the view.
async function openEditor($) {
  const snap = await R.scanCases($);
  const act = R.paneActions($, snap);
  await act.openTerms(snap.cases[0]);
  const view = { tab: 1, selected: CASE_ID, editing: null, terms: T.getTerms(), surface: "terminal" };
  return { snap, act, tree: () => paneTree(ELSC, snap, view, act) };
}

describe("scale.fit", () => {
  test("fit pads at least 4 each side", () => {
    assert.deepEqual(S.fit([100]), { lo: 96, hi: 104 });
    assert.deepEqual(S.fit([98, 102]), { lo: 94, hi: 106 });
  });

  test("fit pads 25 percent of the spread", () => {
    assert.deepEqual(S.fit([800, 1000]), { lo: 750, hi: 1050 });
  });

  test("full range is min minus 50 percent, max plus 50, rounded to 10", () => {
    assert.deepEqual(S.fit([800, 1000], true), { lo: 400, hi: 1500 });
    assert.deepEqual(S.fit([62], true), { lo: 30, hi: 100 });
  });

  test("empty values get a sane default range", () => {
    assert.deepEqual(S.fit([]), { lo: 0, hi: 100 });
  });
});

describe("scale.lanes", () => {
  test("labels within 12 columns stack", () => {
    const out = S.lanes([
      { key: "target", col: 10, label: "target" },
      { key: "walkaway", col: 14, label: "walk-away" },
      { key: "near", col: 16, label: "near" },
      { key: "far", col: 40, label: "far" },
    ]);
    const tier = (k) => out.find((h) => h.key === k).tier;
    assert.equal(tier("target"), 0);
    assert.equal(tier("walkaway"), 1);
    assert.equal(tier("near"), 2);
    assert.equal(tier("far"), 0);
  });

  test("labels 12 columns apart share a row", () => {
    const out = S.lanes([
      { key: "a", col: 5, label: "a" },
      { key: "b", col: 17, label: "b" },
    ]);
    assert.deepEqual(out.map((h) => h.tier), [0, 0]);
  });
});

describe("scale.warnings", () => {
  test("walk-away below target warns the gate would block", () => {
    const w = S.warnings({ target: 900, alternative: 800, walkaway: 850 });
    assert.equal(w.some((s) => /walk-away below target/.test(s)), true);
    assert.equal(w.some((s) => /block every offer/.test(s)), true);
  });

  test("walk-away above target warns for a receive case", () => {
    const w = S.warnings({ target: 900, alternative: 950, walkaway: 1000, direction: "receive" });
    assert.equal(w.some((s) => /walk-away above target/.test(s)), true);
  });

  test("target and walk-away under $3 apart warns little room", () => {
    const w = S.warnings({ target: 900, alternative: 800, walkaway: 901 });
    assert.equal(w.some((s) => /\$3 apart/.test(s)), true);
    assert.equal(w.some((s) => /little room to trade/.test(s)), true);
  });

  test("best alternative above walk-away warns to raise it", () => {
    const w = S.warnings({ target: 800, alternative: 950, walkaway: 900 });
    assert.equal(w.some((s) => /alternative/.test(s) && /walk-away/.test(s)), true);
  });

  test("sound terms warn on nothing", () => {
    assert.deepEqual(S.warnings({ target: 800, alternative: 850, walkaway: 900 }), []);
    assert.deepEqual(S.warnings({}), []);
  });
});

describe("terms editor", () => {
  test("t opens the editor and shows the walk-away plainly", async () => {
    const { $ } = fakeDollar({ files: termsFiles(), dirs: termsDirs() });
    const { tree } = await openEditor($);
    const flat = JSON.stringify(tree());
    assert.notEqual(findNode(tree(), byKey("scale")), null);
    const walk = findNode(tree(), byKey("term-walkaway"));
    assert.equal(walk.props.value, "900");
    assert.equal(findNode(tree(), byKey("term-target")).props.value, "800");
    assert.equal(findNode(tree(), byKey("term-alternative")).props.value, "850");
    assert.match(flat, /offer/);
  });

  test("all three fields follow a drag", async () => {
    const { $ } = fakeDollar({ files: termsFiles(), dirs: termsDirs() });
    const on = fakeOn();
    register(on.on);
    const msg = on.get("ui.message");
    const { act, tree } = await openEditor($);
    const e = (data) => ({
      element: "scale", module: "client/scale-drag.jsx", requestId: "betterterms",
      component: "Pane", data,
    });
    for (const [handle, value] of [["target", 827], ["alternative", 873], ["walkaway", 942]]) {
      await msg($, e({ type: "value", handle, value }), fired().next);
    }
    assert.equal(findNode(tree(), byKey("term-target")).props.value, "827");
    assert.equal(findNode(tree(), byKey("term-alternative")).props.value, "873");
    assert.equal(findNode(tree(), byKey("term-walkaway")).props.value, "942");
  });

  test("fit refits only on release", async () => {
    const { $ } = fakeDollar({ files: termsFiles(), dirs: termsDirs() });
    const on = fakeOn();
    register(on.on);
    const msg = on.get("ui.message");
    await openEditor($);
    const before = { ...T.getTerms().fit };
    const e = (data) => ({
      element: "scale", requestId: "betterterms", component: "Pane", data,
    });
    // A drag post never refits: the range stays put mid-drag.
    await msg($, e({ type: "value", handle: "target", value: 1200 }), fired().next);
    assert.deepEqual(T.getTerms().fit, before);
    // The release refits so the landed value sits inside the range.
    await msg($, e({ type: "release", handle: "target" }), fired().next);
    const after = T.getTerms().fit;
    assert.equal(after.lo <= 1200 && after.hi >= 1200, true);
    assert.notDeepEqual(after, before);
  });

  test("minus and plus nudge by 1", async () => {
    const { $ } = fakeDollar({ files: termsFiles(), dirs: termsDirs() });
    const { act, tree } = await openEditor($);
    await findNode(tree(), byKey("nudge-minus")).props.onPress();
    assert.equal(T.getTerms().target, 799);
    await findNode(tree(), byKey("nudge-plus")).props.onPress();
    assert.equal(T.getTerms().target, 800);
    await act.cycleFocus();
    await findNode(tree(), byKey("nudge-minus")).props.onPress();
    assert.equal(T.getTerms().alternative, 849);
    void act;
  });

  test("z toggles full range", async () => {
    const { $ } = fakeDollar({ files: termsFiles(), dirs: termsDirs() });
    const { tree } = await openEditor($);
    assert.deepEqual(T.getTerms().fit, { lo: 750, hi: 1050 });
    await findNode(tree(), byKey("range-toggle")).props.onPress();
    assert.deepEqual(T.getTerms().fit, { lo: 400, hi: 1500 });
    await findNode(tree(), byKey("range-toggle")).props.onPress();
    assert.deepEqual(T.getTerms().fit, { lo: 750, hi: 1050 });
  });

  test("save writes walk-away through stdin, never argv", async () => {
    const { $, calls } = fakeDollar({
      files: termsFiles(), dirs: termsDirs(),
      run: () => ({ exitCode: 0, stdout: '{"ok":true}', stderr: "" }),
    });
    const { tree } = await openEditor($);
    await findNode(tree(), byKey("save-terms")).props.onPress();
    const floor = calls.run.find((r) => r.argv.includes("set-floor"));
    assert.ok(floor, "set-floor ran");
    assert.equal(floor.init.stdin, "900\n");
    for (const r of calls.run) {
      assert.equal(
        r.argv.some((a) => String(a).includes("900")),
        false,
        `argv leaks the walk-away: ${r.argv.join(" ")}`,
      );
    }
    const terms = calls.run.find((r) => r.argv.includes("set-terms"));
    assert.ok(terms, "set-terms ran");
    assert.deepEqual(terms.argv, [
      "python3", BT, "case", "set-terms", CASE_ID,
      "--target", "800", "--alternative", "850",
      "--period", "month", "--note", "TMobile quote",
    ]);
    assert.equal(calls.toast.some((t) => /terms saved/.test(t)), true);
  });

  test("a refused save toasts the bt.py reason", async () => {
    // A refused command is exit 2 with {"error": ...} on stdout: the
    // toast shows the CLI's own reason, not a bare exit code. A
    // refused set-terms also stops the save before set-floor runs.
    for (const [cmd, reason] of [
      ["set-terms",
        "target is on the wrong side of your walk-away; nothing saved"],
      ["set-floor",
        "walk-away is on the wrong side of your target; nothing saved"],
    ]) {
      const { $, calls } = fakeDollar({
        files: termsFiles(), dirs: termsDirs(),
        run: (argv) => argv.includes(cmd)
          ? { exitCode: 2, stdout: JSON.stringify({ error: reason }), stderr: "" }
          : { exitCode: 0, stdout: '{"ok":true}', stderr: "" },
      });
      const { tree } = await openEditor($);
      await findNode(tree(), byKey("save-terms")).props.onPress();
      assert.equal(
        calls.toast.some((t) => t.includes(reason)), true,
        `toasts: ${calls.toast.join(" | ")}`,
      );
      if (cmd === "set-terms") {
        assert.equal(
          calls.run.some((r) => r.argv.includes("set-floor")), false,
          "a refused set-terms still ran set-floor",
        );
      }
    }
  });
});

describe("savings tab", () => {
  const LEDGER_LINES = [
    '{"case_id":"a-20260101-aaaa","saved_per_year":240,"recorded_at":"2026-09-07T00:00:00Z"}',
    '{"case_id":"b-20260201-bbbb","saved_per_year":-100,"recorded_at":"2026-09-14T00:00:00Z"}',
    '{"case_id":"c-20260301-cccc","saved_per_year":1300,"recorded_at":"2026-09-14T12:00:00Z"}',
  ].join("\n");
  const data = {
    total: { cases: 3, by_currency: { USD: 1440 }, by_pack: {}, warnings: 0 },
    records: [
      { case_id: "a-20260101-aaaa", saved_per_year: 240, recorded_at: "2026-09-07T00:00:00Z" },
      { case_id: "b-20260201-bbbb", saved_per_year: -100, recorded_at: "2026-09-14T00:00:00Z" },
      { case_id: "c-20260301-cccc", saved_per_year: 1300, recorded_at: "2026-09-14T12:00:00Z" },
    ],
  };

  test("savings draws Svg on desktop and Raster on terminal", () => {
    const desk = V.savingsBody(ELSSVG, data, "desktop");
    assert.notEqual(findNode(desk, byTag("Svg")), null);
    assert.equal(findNode(desk, byTag("Raster")), null);
    const term = V.savingsBody(ELSR, data, "terminal");
    assert.notEqual(findNode(term, byTag("Raster")), null);
    assert.equal(findNode(term, byTag("Svg")), null);
    // Neither chart element on vscode or mobile: plain text only.
    const remote = V.savingsBody(ELS, data, "vscode");
    assert.equal(findNode(remote, byTag("Svg")), null);
    assert.equal(findNode(remote, byTag("Raster")), null);
    assert.match(JSON.stringify(remote), /1440/);
  });

  test("summary line counts closed, walked away and average", () => {
    const flat = JSON.stringify(V.savingsBody(ELSR, data, "terminal"));
    assert.match(flat, /3 closed/);
    assert.match(flat, /1 walked away/);
    assert.match(flat, /\$480\/yr average/);
  });

  test("weekly series is cumulative", () => {
    const w = V.weeks(data.records);
    assert.deepEqual(w.map((x) => x.cum), [240, 1440]);
  });

  test("mixed currencies never add into one total", () => {
    const mixed = {
      total: { cases: 2, by_currency: { USD: 1440, EUR: 200 }, by_pack: {}, warnings: 0 },
      records: [
        ...data.records.map((r) => ({ ...r, currency: "USD" })),
        { case_id: "d-20260305-dddd", saved_per_year: 200, currency: "EUR", recorded_at: "2026-09-21T00:00:00Z" },
      ],
    };
    const flat = JSON.stringify(V.savingsBody(ELSR, mixed, "vscode"));
    assert.match(flat, /saved \$1440\/yr · EUR 200\/yr/);
    assert.doesNotMatch(flat, /1640/);
    // The chart tracks one currency and says so.
    assert.match(flat, /chart shows USD/);
  });

  test("one-time savings show as once, never fold into per-year", () => {
    const once = {
      total: {
        cases: 2,
        by_currency: { USD: 120 },
        once_by_currency: { USD: 100 },
        by_pack: {}, warnings: 0,
      },
      records: [
        { case_id: "a-20260101-aaaa", saved_per_year: 120, saved_once: 0, recorded_at: "2026-09-07T00:00:00Z" },
        { case_id: "b-20260201-bbbb", saved_per_year: 0, saved_once: 100, recorded_at: "2026-09-14T00:00:00Z" },
      ],
    };
    const flat = JSON.stringify(V.savingsBody(ELSR, once, "vscode"));
    assert.match(flat, /saved \$120\/yr/);
    assert.match(flat, /\$100 once/);
    assert.doesNotMatch(flat, /\$220/);
    // The per-year average does not count the once amount either.
    assert.match(flat, /\$120\/yr average/);
  });

  test("parseRecords carries saved_once on its own field", () => {
    const recs = V.parseRecords([
      '{"case_id":"a-20260101-aaaa","saved_once":100,"currency":"EUR"}',
      '{"case_id":"b-20260101-bbbb","saved_per_year":1200}',
      '{"case_id":"c-20260101-cccc"}',
    ].join("\n"));
    assert.equal(recs.length, 2);
    assert.equal(recs[0].saved_once, 100);
    assert.equal(recs[0].saved_per_year, 0);
    assert.equal(recs[0].currency, "EUR");
    assert.equal(recs[1].saved_once, 0);
    assert.equal(recs[1].saved_per_year, 1200);
  });

  test("the chart alt text names the currency it draws", () => {
    const desk = V.savingsBody(ELSSVG, data, "desktop");
    const svg = findNode(desk, byTag("Svg"));
    assert.match(svg.props.alt, /USD/);
  });

  test("empty ledger draws a real empty state, not $0 scaffolding", () => {
    const empty = { total: { cases: 0, by_currency: {} }, records: [] };
    const tree = V.savingsBody(ELSR, empty, "terminal");
    const flat = JSON.stringify(tree);
    assert.match(flat, /no savings recorded yet/);
    assert.doesNotMatch(flat, /\$0\/yr/);
    assert.equal(findNode(tree, byTag("Raster")), null);
  });

  test("savingsData runs bt ledger total and reads ledger.jsonl", async () => {
    const files = termsFiles({ "/bt/ledger.jsonl": LEDGER_LINES });
    const { $, calls } = fakeDollar({
      files, dirs: termsDirs(),
      run: () => ({ exitCode: 0, stdout: LEDGER_TOTAL, stderr: "" }),
    });
    const snap = await R.scanCases($);
    const act = R.paneActions($, snap);
    const got = await act.savingsData();
    assert.equal(calls.run.some((r) => r.argv.join(" ").includes("ledger total")), true);
    assert.equal(got.total.by_currency.USD, 1440);
    assert.equal(got.records.length, 3);
  });
});
