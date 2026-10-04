// betterterms-mod: the opt-in Claude Code mod for betterterms.
//
// A function-hook plugin: hooks/hooks.json names this file (modules
// resolve relative to hooks/, hence "../register.js") and the engine
// calls register(on) once at load. session.start registers
// /betterterms (alias /betterterms-cases), opens the pane when cases
// exist, baselines inbound entries, sets the status line and starts
// the 3s poll. tool.call is the pre-send guard: a call carrying an
// open case's last gate.json `rendered` text re-gates through
// `python3 bt.py gate`; needs_approval is denied to the pane, and the
// hook's .catch denies any plausible send it failed over. ui.render
// draws the AbovePrompt band, the three-tab Pane (Cases, Approvals,
// Savings; the cases tab hosts the terms editor of spec 6.4) and the
// gate rows; ui.message relays the price-scale Client's posts;
// command.run opens the pane.
//
// The loader follows `$` only into this file's top-level functions,
// never across an import. So every $ member the mod needs is bound
// once into the `host` facade below, each spelled `$.noun.event(...)`
// with literal names where the audit requires them, and lib/*.js
// does the work over that plain object (the pattern the bundled diff
// mod uses for its Host).

import * as C from "./lib/cases.js";
import * as A from "./lib/approvals.js";
import * as IO from "./lib/hostio.js";
import * as S from "./lib/scan.js";
import * as W from "./lib/wiring.js";
import * as T from "./ui/terms.js";
import { paneTree } from "./ui/pane.js";
import { bandTree } from "./ui/band.js";
import { gateRow } from "./ui/rows.js";

const PANE_ID = "betterterms";
// $.state refs must be literals of this file for the audit to list them.
const REF_TAB = { plugin: "betterterms-mod", key: "tab" };
const REF_SELECTED = { plugin: "betterterms-mod", key: "selected" };
const REF_APPROVALS = { plugin: "betterterms-mod", key: "approvals" };

// The facade lib/hostio.js and lib/wiring.js work through. Every $ the
// mod touches appears exactly once here, literal where the audit asks
// (env names, state refs) and variable elsewhere (paths, argv, text).
export function hostOf($) {
  return {
    pluginRoot: $.plugin.root,
    envBtHome: () => $.env.get("BETTERTERMS_HOME"),
    envHome: () => $.env.get("HOME"),
    fsRead: (p) => $.fs.read(p),
    fsWrite: (p, t) => $.fs.write(p, t),
    fsStat: (p, i) => $.fs.stat(p, i),
    fsList: (p) => $.fs.list(p),
    fsExists: (p) => $.fs.exists(p),
    procRun: (argv, init) => $.process.run(argv, init),
    stateTab: () => $.state.get(REF_TAB),
    setTab: (v) => $.state.set(REF_TAB, v),
    stateSelected: () => $.state.get(REF_SELECTED),
    setSelected: (v) => $.state.set(REF_SELECTED, v),
    stateApprovals: () => $.state.get(REF_APPROVALS),
    setApprovals: (v, init) => $.state.set(REF_APPROVALS, v, init),
    toast: (t) => $.ui.toast(t),
    status: (t) => $.ui.status(t),
    notice: (id, t) => $.ui.notice(id, t),
    invalidate: () => $.ui.invalidate("ui.render"),
    openPane: (r) => $.ui.open(r),
    ask: (q, i) => $.ui.ask(q, i),
    submit: (e) => $.prompt.submit(e),
    registerCommand: (s) => $.command.register(s),
    every: (ms, fn) => $.clock.every(ms, fn),
  };
}

// Exported for the unit suites (they drive the same facade the engine
// sees): the scan every hook shares and the pane's action set.
export const scanCases = ($) => S.scanCases(hostOf($));
export const paneActions = ($, snap) => W.paneActions(hostOf($), snap);

// Strings worth scanning: long enough to carry a draft, or naming a case id.
const plausible = (ss) => ss.some((s) => s.length >= C.SEND_MIN_CHARS || /-\d{8}-/.test(s));

export function register(on) {
  IO.resetBt();
  S.resetScan();
  on("session.start", async ($, e, next) => W.sessionStart(hostOf($), e, next));

  on("command.run", { command: "betterterms" }, ($) => W.runCommand(hostOf($)));
  on("command.run", { command: "betterterms-cases" }, ($) => W.runCommand(hostOf($)));

  on("tool.call", async ($, e, next) => {
    // The agent's own approval question is not a send; gating it would
    // put our ask in front of its ask.
    if (e.tool === "AskUserQuestion") return next(e);
    const strings = C.collectStrings(C.callArgs(e));
    if (!plausible(strings)) return next(e);
    const host = hostOf($);
    const snap = await S.scanCases(host);
    if (snap.cases.length === 0) return next(e);
    if (await W.isCaseWrite(host, snap, e)) return next(e);
    const hit = C.findSend(strings, snap.cases);
    if (hit === null) return next(e);
    return W.gateSend(host, snap, hit, e, next);
  }).catch(($, e, next) => {
    if (next.called || !plausible(C.collectStrings(C.callArgs(e)))) return next(e);
    // A failed hook must never let a send through (spec 6.3).
    return { deny: "betterterms: the send check failed; the draft was not sent" };
  });

  // A typed `bt approve` is a user action: the settings hook writes
  // the marker while this hook records the hash in $.state, the one
  // place the send check trusts.
  on("prompt.submit", async ($, e, next) =>
    W.promptSubmit(hostOf($), e, next));

  on("ui.render", { component: "AbovePrompt" }, async ($, e, next) => {
    if (e.props?.hasSurvey) return next(e);
    const host = hostOf($);
    // A redraw or drag storm may call this many times inside the
    // burst window; the scan is fingerprint-cached anyway.
    const snap = await S.scanCases(host, { burst: true }).catch(() => A.EMPTY_SNAP);
    const counts = {
      held: C.heldTotal(snap.cases),
      pending: C.pendingWithoutHeld(snap.cases),
      // A case counts as replied only while its last turn is inbound;
      // an answer in another channel clears it without waiting a tick.
      repliers: W.repliedCases(snap),
    };
    const el = $.ui.resolve(e);
    return bandTree(el, counts, () => W.paneActions(host, snap).openTab(2)) ?? next(e);
  });

  on("ui.render", { component: "Pane", requestId: PANE_ID }, async ($, e) => {
    const el = $.ui.resolve(e);
    const host = hostOf($);
    const snap = await S.scanCases(host, { burst: true }).catch(() => A.EMPTY_SNAP);
    const act = W.paneActions(host, snap);
    const view = {
      tab: await W.getTab(host),
      selected: await W.getSelected(host),
      editing: A.getEditing(),
      terms: T.getTerms(),
      surface: e.surface,
      savings: undefined,
    };
    if (view.tab === 3) view.savings = await act.savingsData().catch(() => null);
    return paneTree(el, snap, view, act);
  });

  on("ui.render", { component: "ToolUse" }, async ($, e, next) => {
    const row = gateRow(e.props ?? {});
    if (row === null) return next(e);
    const { Text } = $.ui.resolve(e);
    return h(Text, { color: row.color }, row.text);
  });

  // The terms editor's Client posts (drag values, focus, nudges, the
  // z toggle and save) arrive here. Anything not ours defers.
  on("ui.message", async ($, e, next) => {
    if (e?.element !== "scale" || e?.data === null || typeof e.data !== "object") {
      return next(e);
    }
    return T.scaleMessage(hostOf($), e);
  });
}
