// The terms editor (spec 6.4): one price scale with target, best
// alternative and walk-away handles plus the counterparty's current
// offer as a fixed marker. `t` opens it on a case, `s` saves.
//
// The walk-away is shown plainly in this pane by owner decision
// (2026-10-04): the pane is drawn for the user and is not sent to the
// model. It enters `terms` only through a `.floor` read at open and
// leaves only as stdin to `bt.py case set-floor`; it never appears in
// argv, in any file the agent reads, or in gate or ledger output.

import * as C from "../lib/cases.js";
import * as IO from "../lib/hostio.js";
import * as S from "./scale.js";

const HANDLE_KEYS = new Set(["target", "alternative", "walkaway"]);
const TAB_ORDER = ["target", "alternative", "walkaway"];
const HANDLES = [
  { key: "target", mark: "T", color: "green", label: "target" },
  { key: "alternative", mark: "A", color: "blue", label: "alternative" },
  { key: "walkaway", mark: "W", color: "red", label: "walk-away" },
];

// The one in-flight edit, like approvals.js's `editing`: {caseId,
// dir, home, direction, currency, target, alternative, walkaway,
// offer, altPeriod, altNote, focus, full, saved, fit:{lo,hi}}.
let terms = null;
export function getTerms() { return terms; }
export function clearTerms() { terms = null; }

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
};
// Field text like "$1,200.50" or "1200" to a number, else null.
const parseField = (raw) => num(String(raw ?? "").replace(/[$,\s]/g, ""));
// A value as argv/field text: integers stay integers, cents round to 2.
const amt = (v) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100));
const fitValues = (t) =>
  [t.target, t.alternative, t.walkaway, t.offer].filter(Number.isFinite);
const refit = (t) => { t.fit = S.fit(fitValues(t), t.full); };

// plan.yaml -> the seeded editor: target and best_alternative come
// from the plan, the offer marker from deriveCase's offerMarks.
export function seedTerms(c, planText, floor, direction) {
  const plan = C.parseFlatYaml(planText);
  const alt = plan.best_alternative;
  const t = {
    caseId: c.id,
    dir: null,
    home: null,
    direction: direction === "receive" ? "receive" : "pay",
    currency: String(plan.currency ?? c.offer?.currency ?? "USD"),
    target: num(c.offer?.target ?? plan.target),
    alternative: num(alt && typeof alt === "object" ? alt.amount : alt),
    walkaway: num(floor),
    offer: num(c.offer?.offer ?? c.offer?.start),
    altPeriod: alt && typeof alt === "object" && typeof alt.period === "string" ? alt.period : null,
    altNote: alt && typeof alt === "object" && typeof alt.note === "string" ? alt.note : null,
    focus: "target",
    full: false,
    saved: false,
    fit: { lo: 0, hi: 100 },
  };
  refit(t);
  return t;
}

// `t` on a case. The .floor read exists only to show the user their
// own walk-away; nothing else in the mod touches that file.
export async function openTerms(host, snap, c) {
  const dir = `${snap.root}/${c.id}`;
  const [planText, floorText, briefText] = await Promise.all([
    IO.readIf(host, `${dir}/plan.yaml`),
    IO.readIf(host, `${dir}/.floor`),
    IO.readIf(host, `${dir}/brief.yaml`),
  ]);
  const direction = C.parseFlatYaml(briefText).direction;
  terms = seedTerms(c, planText, num(String(floorText ?? "").trim()), direction);
  terms.dir = dir;
  terms.home = snap.home;
  host.invalidate("ui.render");
}

// A typed number field committed: parse, store, refit (a discrete
// change, not a drag), redraw.
export function setTermField(host, handle, raw) {
  if (!terms || !HANDLE_KEYS.has(handle)) return;
  terms[handle] = parseField(raw);
  terms.saved = false;
  refit(terms);
  host.invalidate("ui.render");
}

// -/+ nudges the focused handle by $1.
export function nudgeField(host, delta) {
  if (!terms) return;
  const handle = terms.focus;
  const v = (terms[handle] ?? 0) + delta;
  terms[handle] = v > 0 ? v : null;
  terms.saved = false;
  refit(terms);
  host.invalidate("ui.render");
}

export function cycleFocus(host) {
  if (!terms) return;
  const i = TAB_ORDER.indexOf(terms.focus);
  terms.focus = TAB_ORDER[(i + 1) % TAB_ORDER.length];
  host.invalidate("ui.render");
}

export function toggleRange(host) {
  if (!terms) return;
  terms.full = !terms.full;
  refit(terms);
  host.invalidate("ui.render");
}

export function closeTerms(host) {
  terms = null;
  host.invalidate("ui.render");
}

// The reason a failed bt.py call prints: a refused command is exit 2
// with {"error": "..."} on stdout, so the toast shows the CLI's own
// words (like the wrong-side refusals), not a bare exit code.
const btError = (p) => {
  if (p?.error) return p.error;
  try {
    const out = JSON.parse(p?.stdout ?? "");
    if (typeof out?.error === "string") return out.error;
  } catch { /* stdout was not JSON */ }
  return p?.stderr || `exit ${p?.exitCode}`;
};

// s: target and best alternative land in plan.yaml through
// `case set-terms`; the walk-away goes to `case set-floor` on stdin,
// never argv (spec 6.4). A missing walk-away refuses, since the gate
// would have nothing to hold.
export async function saveTerms(host) {
  const t = terms;
  if (!t?.dir) return;
  const bt = await IO.findBt(host);
  if (bt === null) {
    host.toast("betterterms: bt.py not found; install the betterterms plugin");
    return;
  }
  if (t.walkaway === null) {
    host.toast("betterterms: enter a walk-away before saving");
    return;
  }
  const argv = ["python3", bt, "case", "set-terms", t.caseId];
  if (t.target !== null) argv.push("--target", amt(t.target));
  if (t.alternative !== null) argv.push("--alternative", amt(t.alternative));
  if (t.altPeriod !== null) argv.push("--period", t.altPeriod);
  if (t.altNote !== null) argv.push("--note", t.altNote);
  let fail = null;
  if (argv.length > 6) {
    const p = await IO.runProc(host, t.home, argv);
    if (p?.error || p?.exitCode !== 0) fail = btError(p);
  }
  if (fail === null) {
    const p = await IO.runProc(host, t.home,
      ["python3", bt, "case", "set-floor", t.caseId],
      { stdin: `${amt(t.walkaway)}\n` });
    if (p?.error || p?.exitCode !== 0) fail = btError(p);
  }
  t.saved = fail === null;
  host.toast(t.saved
    ? `betterterms: terms saved for ${t.caseId}`
    : `betterterms: save failed: ${String(fail).slice(0, 120)}`);
  host.invalidate("ui.render");
}

// The Client's posts arrive as ui.message (element "scale"). A mid-
// drag "value" updates the field without refitting; "release" refits.
export async function scaleMessage(host, e) {
  const d = e?.data;
  if (terms === null || d === null || typeof d !== "object") return {};
  if (d.type === "value" && HANDLE_KEYS.has(d.handle) && typeof d.value === "number" && d.value > 0) {
    terms[d.handle] = Math.round(d.value);
    terms.saved = false;
    host.invalidate("ui.render");
  } else if (d.type === "focus" && HANDLE_KEYS.has(d.handle)) {
    terms.focus = d.handle;
    host.invalidate("ui.render");
  } else if (d.type === "release") {
    refit(terms);
    host.invalidate("ui.render");
  } else if (d.type === "nudge" && typeof d.delta === "number") {
    nudgeField(host, d.delta);
  } else if (d.type === "full") {
    toggleRange(host);
  } else if (d.type === "save") {
    await saveTerms(host);
  }
  return {};
}

// The scale without a Client (vscode, mobile): the same barCells the
// Client draws, as one plain Text line.
function textBar(el, t) {
  const cells = S.barCells({
    values: { target: t.target, alternative: t.alternative, walkaway: t.walkaway },
    offer: t.offer, lo: t.fit.lo, hi: t.fit.hi, cols: 40, handles: HANDLES,
  });
  return h(el.Text, { key: "terms-bar", dimColor: true }, cells.map((c) => c.ch).join(""));
}

export function termsTree(el, t, act) {
  const { Box, Text, Button } = el;
  const rows = [
    h(Text, { key: "terms-h", dimColor: true },
      `terms for ${t.caseId} · drag, type, tab + -/+ nudge, z range, s save, c close${t.saved ? " · saved" : ""}`),
  ];
  if (el.Client) {
    // The module path must be a string literal for the loader.
    rows.push(h(el.Client, {
      key: "scale",
      module: "../client/scale-drag.jsx",
      props: {
        lo: t.fit.lo,
        hi: t.fit.hi,
        values: { target: t.target, alternative: t.alternative, walkaway: t.walkaway },
        offer: t.offer,
        focused: t.focus,
        currency: t.currency,
      },
      width: 40,
      height: 4,
    }));
  } else {
    rows.push(textBar(el, t));
  }
  if (el.Input) {
    for (const hd of HANDLES) {
      rows.push(h(el.Input, {
        key: `term-${hd.key}`,
        label: `${hd.label} `,
        value: t[hd.key] === null ? "" : amt(t[hd.key]),
        submitLabel: "set",
        onSubmit: (raw) => act.setTerm(hd.key, raw),
      }));
    }
  }
  S.warnings({
    target: t.target, alternative: t.alternative,
    walkaway: t.walkaway, direction: t.direction,
  }).forEach((w, i) => {
    rows.push(h(Text, { key: `warn-${i}`, dimColor: true }, `! ${w}`));
  });
  rows.push(h(Text, { key: "terms-f", dimColor: true }, `focus: ${t.focus}`));
  rows.push(h(
    Box,
    { key: "terms-b" },
    h(Button, { key: "nudge-minus", label: "-", onPress: () => act.nudge(-1) }),
    h(el.Text, null, " "),
    h(Button, { key: "nudge-plus", label: "+", onPress: () => act.nudge(1) }),
    h(el.Text, null, " "),
    h(Button, { key: "focus-next", label: "next", hotkey: "f", onPress: () => act.cycleFocus() }),
    h(el.Text, null, " "),
    h(Button, { key: "range-toggle", label: "range", hotkey: "z", onPress: () => act.toggleRange() }),
    h(el.Text, null, " "),
    h(Button, {
      key: "save-terms", label: "Save", hotkey: "s", variant: "primary",
      onPress: () => act.saveTerms(),
    }),
    h(el.Text, null, " "),
    h(Button, { key: "terms-close", label: "Close", hotkey: "c", onPress: () => act.closeTerms() }),
  ));
  return h(Box, { key: "terms", flexDirection: "column" }, ...rows);
}
