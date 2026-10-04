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
// draws the AbovePrompt band, the three-tab Pane and the gate rows;
// command.run opens the pane.
//
// The loader follows `$` only into this file's top-level functions,
// never across an import, so `$`-touching helpers live here and
// lib/*.js stays pure. The module-scope sets exist for the same
// reason; session.start reseeds them so a reload does not toast twice.

import * as C from "./lib/cases.js";
import * as A from "./lib/approvals.js";
import { paneTree } from "./ui/pane.js";
import { bandTree } from "./ui/band.js";
import { gateRow } from "./ui/rows.js";

const PANE_ID = "betterterms";
const POLL_MS = 3000;
// $.state refs must be literals of this file for the audit to list them.
const REF_TAB = { plugin: "betterterms-mod", key: "tab" };
const REF_SELECTED = { plugin: "betterterms-mod", key: "selected" };
const REF_APPROVALS = { plugin: "betterterms-mod", key: "approvals" };

const seen = new Map();
const replied = new Set();
let lastPrint = "", lastStatus = "";

async function homeDir($) {
  const env = await $.env.get("BETTERTERMS_HOME");
  if (env !== undefined && env !== "") return env;
  const home = await $.env.get("HOME");
  return home === undefined || home === "" ? null : `${home}/.betterterms`;
}

async function readIf($, path) {
  try { return await $.fs.read(path); } catch { return undefined; }
}

async function statIf($, path, init) {
  try { return await $.fs.stat(path, init); } catch { return undefined; }
}

async function listIf($, path) {
  try { return await $.fs.list(path); } catch { return []; }
}

// held/<hash>.yaml files, oldest first, .approved flags read.
async function heldForCase($, dir) {
  const ents = await listIf($, `${dir}/held`);
  const ok = (e) => e.kind === "file";
  const approved = new Set(
    ents.filter((e) => ok(e) && /\.approved$/.test(e.name ?? ""))
      .map((e) => e.name.slice(0, -".approved".length)),
  );
  const held = [];
  for (const ent of ents) {
    const name = String(ent.name ?? "");
    if (!ok(ent) || !/^[0-9a-f]{64}\.yaml$/.test(name)) continue;
    const parsed = A.parseHeldFile(await readIf($, `${dir}/held/${name}`));
    if (parsed) held.push({ ...parsed, approved: approved.has(parsed.hash) });
  }
  held.sort((a, b) => a.heldAt.localeCompare(b.heldAt) || a.hash.localeCompare(b.hash));
  return held;
}

// The case-folder snapshot every hook draws from: brief, plan (the
// offer bar's targets), thread, draft, gate.json, held/, ledger.
// .floor is never touched.
export async function scanCases($) {
  const home = await homeDir($);
  if (home === null) return A.EMPTY_SNAP;
  const ledger = C.parseLedger((await readIf($, `${home}/ledger.jsonl`)) ?? "");
  const root = `${home}/cases`;
  const rootStat = await statIf($, root, { resolve: true });
  if (rootStat?.kind !== "dir") {
    return { home, root, resolvedRoot: null, cases: [], savedPerYear: ledger.savedPerYear };
  }
  const cases = [];
  for (const ent of await listIf($, root)) {
    if (ent.kind !== "dir" || ent.isLink || !C.safeCaseId(ent.name)) continue;
    const dir = `${root}/${ent.name}`;
    const read = (n) => readIf($, `${dir}/${n}`);
    const stat = (n) => statIf($, `${dir}/${n}`);
    const texts = ["brief.yaml", "thread.md", "draft.yaml", "gate.json", "plan.yaml"];
    const [briefText, threadText, draftText, gateText, planText] =
      await Promise.all(texts.map(read));
    const names = ["draft.yaml", "gate.json", "thread.md"];
    const [draftSt, gateSt, threadSt] = await Promise.all(names.map(stat));
    const [sources, held] = await Promise.all([listIf($, `${dir}/sources`), heldForCase($, dir)]);
    cases.push(C.deriveCase({
      id: ent.name,
      briefText, threadText, draftText, gateText, planText,
      draftMtimeMs: draftSt?.mtimeMs ?? 0,
      gateMtimeMs: gateSt?.mtimeMs ?? 0,
      threadMtimeMs: threadSt?.mtimeMs ?? 0,
      sourceCount: sources.length,
      closed: ledger.closed.has(ent.name),
      held,
    }));
  }
  return { home, root, resolvedRoot: rootStat.realPath ?? root, cases, savedPerYear: ledger.savedPerYear };
}

// bt.py lives in the core plugin's skill tree, probed once per call.
async function findBt($) {
  for (const p of C.btPaths($.plugin.root)) {
    if (await $.fs.exists(p)) return p;
  }
  return null;
}

// A write whose path resolves inside a case dir is bookkeeping, not a
// send; the resolve stops a link under cases/ masquerading as one.
async function isCaseWrite($, snap, e) {
  const fp = e.file_path ?? e.path ?? e.notebook_path;
  if (typeof fp !== "string" || snap.resolvedRoot == null) return false;
  let real = (await statIf($, fp, { resolve: true }))?.realPath;
  if (real === undefined) {
    const idx = fp.lastIndexOf("/");
    if (idx <= 0) return false;
    const parent = await statIf($, fp.slice(0, idx), { resolve: true });
    if (parent?.realPath === undefined) return false;
    real = `${parent.realPath}${fp.slice(idx)}`;
  }
  return real === snap.resolvedRoot || real.startsWith(`${snap.resolvedRoot}/`);
}

async function runProc($, snap, argv) {
  const env = snap.home === null ? undefined : { BETTERTERMS_HOME: snap.home };
  try {
    return await $.process.run(argv, { env, timeoutMs: A.GATE_TIMEOUT_MS });
  } catch (err) {
    return { error: String(err?.message ?? err).slice(0, 200) };
  }
}

async function runGate($, snap, c, approved) {
  const dir = `${snap.root}/${c.id}`;
  const bt = await findBt($);
  if (bt === null) return { result: "error", reasons: ["bt.py not found beside the mod; install the betterterms plugin"] };
  const inbound = await $.fs.exists(`${dir}/inbound.yaml`);
  const proc = await runProc($, snap, C.gateArgv(bt, dir, c.id, { inbound, approved }));
  if (proc.error) return { result: "error", reasons: [`gate run failed: ${proc.error}`] };
  try {
    const out = JSON.parse(proc.stdout);
    return {
      result: typeof out.result === "string" ? out.result : "error",
      reasons: Array.isArray(out.reasons) ? out.reasons.map(String) : [],
      rendered: typeof out.rendered === "string" ? out.rendered : null,
      hash: typeof out.hash === "string" ? out.hash : null,
    };
  } catch {
    return { result: "error", reasons: [(proc.stderr || `gate exit ${proc.exitCode}`).slice(0, 200)] };
  }
}

async function runHeld($, snap, verb, caseId, hash) {
  const bt = await findBt($);
  if (bt === null) return { ok: false, error: "bt.py not found; install the betterterms plugin" };
  const h8 = A.hash8(hash);
  if (h8 === null) return { ok: false, error: "the held draft carries no hash" };
  const proc = await runProc($, snap, ["python3", bt, "held", verb, caseId, h8]);
  if (proc.error) return { ok: false, error: proc.error };
  let out = null;
  try { out = JSON.parse(proc.stdout); } catch { /* stderr carries it */ }
  if (proc.exitCode !== 0 || out?.ok !== true) {
    return { ok: false, error: String(out?.error ?? proc.stderr ?? `exit ${proc.exitCode}`).slice(0, 200) };
  }
  return { ok: true, hash: typeof out.hash === "string" ? out.hash : hash };
}

async function getTab($) {
  const { value } = await $.state.get(REF_TAB).catch(() => ({ value: undefined }));
  return value === 2 || value === 3 ? value : 1;
}

async function getSelected($) {
  const { value } = await $.state.get(REF_SELECTED).catch(() => ({ value: undefined }));
  return typeof value === "string" ? value : null;
}

// Record the press: the full hash goes into $.state.approvals. This is
// the only writer; nothing else may mint an approval.
async function markApproved($, hash) {
  const { value } = await $.state.get(REF_APPROVALS).catch(() => ({ value: undefined }));
  await $.state.set(REF_APPROVALS, { ...(value ?? {}), [hash]: true });
}

// True once per approval: the entry is removed as it is read, so a
// second send of the same text is held again. A write that did not
// land (version drift, a throw) is not a take: fail closed.
async function takeApproval($, hash) {
  const { value, version } =
    await $.state.get(REF_APPROVALS).catch(() => ({ value: undefined, version: 0 }));
  if (value == null || typeof value !== "object" || value[hash] !== true) return false;
  const next = { ...value };
  delete next[hash];
  const res = await $.state.set(REF_APPROVALS, next, { ifVersion: version })
    .catch(() => undefined);
  return res != null && res.isSet !== false;
}

// The pane's Button/Input handlers; the gate's hash check covers a
// stale snapshot.
export function paneActions($, snap) {
  return {
    openTab: async (n) => {
      await $.state.set(REF_TAB, n === 2 || n === 3 ? n : 1);
      await $.ui.open({ id: PANE_ID, title: "betterterms", focus: true }).catch(() => {});
    },
    select: async (id) => {
      const cur = await getSelected($);
      await $.state.set(REF_SELECTED, cur === id ? null : id);
    },
    approve: async (c, held) => {
      const res = await runHeld($, snap, "approve", c.id, held.hash);
      if (!res.ok) return $.ui.toast(`betterterms: approve failed: ${res.error}`);
      await markApproved($, res.hash);
      // A failed submit still leaves the approval recorded; the user
      // can resend the draft by hand and the hash check carries it.
      await $.prompt.submit({ text: A.approvePromptText(res.hash, c.id) }).catch(() =>
        $.ui.toast(`betterterms: approved ${A.hash8(res.hash)}; resend the draft`));
    },
    reject: async (c, held) => {
      const res = await runHeld($, snap, "reject", c.id, held.hash);
      if (!res.ok) return $.ui.toast(`betterterms: reject failed: ${res.error}`);
      $.ui.toast(`betterterms: draft ${A.hash8(held.hash)} rejected`);
      $.ui.invalidate("ui.render");
    },
    edit: (held) => {
      A.setEditing(held.hash);
      $.ui.invalidate("ui.render");
    },
    saveEdit: async (c, held, text) => {
      A.setEditing(null);
      await $.fs.write(`${snap.root}/${c.id}/draft.yaml`, A.draftYaml(c, held, text)).catch(() => {});
      await runGate($, snap, c, false);
      $.ui.invalidate("ui.render");
    },
  };
}

// Strings worth scanning: long enough to carry a draft, or naming a case id.
const plausible = (ss) => ss.some((s) => s.length >= C.SEND_MIN_CHARS || /-\d{8}-/.test(s));

async function gateSend($, snap, c, e, next) {
  const gate = await runGate($, snap, c, false);
  const verdict = C.decideSend(gate, c);
  if (verdict.kind === "deny") {
    $.ui.toast(`betterterms: draft for ${c.id} blocked by the gate`);
    return { deny: `betterterms gate: ${verdict.reason}` };
  }
  if (verdict.kind === "held") {
    if (verdict.hash !== null && (await takeApproval($, verdict.hash))) {
      const again = await runGate($, snap, c, true);
      if (again.result !== "pass") {
        return { deny: `betterterms gate: ${(again.reasons ?? []).join("; ") || "not pass after approval"}` };
      }
      $.ui.notice(e.tool_use_id, "betterterms: approved, gate pass");
      $.ui.toast(`betterterms: draft for ${c.id} sent`);
      return next(e);
    }
    $.ui.invalidate("ui.render");
    return { deny: A.heldDenyText(verdict.hash) };
  }
  if (verdict.kind === "allow") {
    $.ui.notice(e.tool_use_id, "betterterms: gate pass");
    $.ui.toast(`betterterms: draft for ${c.id} sent`);
    return next(e);
  }
  const answer = await $.ui.ask(verdict.question, { options: ["Send", "Hold"], header: "betterterms" })
    .catch(() => null);
  if (answer !== "Send") return { deny: "betterterms: send held; not approved" };
  $.ui.notice(e.tool_use_id, "betterterms: approved, gate pass");
  return next(e);
}

async function tick($) {
  const snap = await scanCases($);
  for (const c of snap.cases) {
    const s = seen.get(c.id) ?? seen.set(c.id, new Set()).get(c.id);
    const fresh = C.newInbound(c.entries, s);
    if (fresh.length > 0) {
      for (const f of fresh) s.add(C.entryKey(f));
      $.ui.toast(C.toastText(c.id, fresh.length));
      replied.add(c.id);
    }
    // Once the agent answers, the case drops out of the band's reply bit.
    if (c.lastDir === "out") replied.delete(c.id);
  }
  const status = A.statusText(snap.cases.length, snap.savedPerYear);
  if (snap.home !== null && status !== lastStatus) {
    lastStatus = status;
    $.ui.status(status);
  }
  const print = JSON.stringify(snap.cases.map((c) => [
    c.id, c.stage, c.pending, c.needsApproval,
    (c.held ?? []).map((held) => held.hash.slice(0, 8)).join(","),
  ]));
  if (print !== lastPrint) {
    lastPrint = print;
    $.ui.invalidate("ui.render");
  }
}

async function runCommand($) {
  const opened = await $.ui.open({ id: PANE_ID, title: "betterterms", focus: true })
    .catch(() => ({ isPlaced: false }));
  return {
    text: opened.isPlaced
      ? "betterterms: cockpit shown."
      : "betterterms: the pane waits for a wider terminal.",
  };
}

export function register(on) {
  on("session.start", async ($, e, next) => {
    const spec = (name, description) =>
      $.command.register({ name, description }).catch(() => {});
    await spec("betterterms", "Open the betterterms cockpit");
    await spec("betterterms-cases", "Open the betterterms cockpit (case list)");
    const snap = await scanCases($).catch(() => A.EMPTY_SNAP);
    seen.clear();
    replied.clear();
    for (const c of snap.cases) {
      seen.set(c.id, new Set(c.entries.filter((x) => x.dir === "in").map(C.entryKey)));
      if (c.lastDir === "in") replied.add(c.id);
    }
    if (snap.cases.length > 0) {
      void $.ui.open({ id: PANE_ID, title: "betterterms" }).catch(() => {});
    }
    lastPrint = "";
    lastStatus = "";
    if (snap.home !== null) {
      lastStatus = A.statusText(snap.cases.length, snap.savedPerYear);
      $.ui.status(lastStatus);
    }
    $.clock.every(POLL_MS, () => tick($).catch(() => {}));
    return next(e);
  });

  on("command.run", { command: "betterterms" }, runCommand);
  on("command.run", { command: "betterterms-cases" }, runCommand);

  on("tool.call", async ($, e, next) => {
    // The agent's own approval question is not a send; gating it would
    // put our ask in front of its ask.
    if (e.tool === "AskUserQuestion") return next(e);
    const strings = C.collectStrings(C.callArgs(e));
    if (!plausible(strings)) return next(e);
    const snap = await scanCases($);
    if (snap.cases.length === 0) return next(e);
    if (await isCaseWrite($, snap, e)) return next(e);
    const hit = C.findSend(strings, snap.cases);
    if (hit === null) return next(e);
    return gateSend($, snap, hit, e, next);
  }).catch(($, e, next) => {
    if (next.called || !plausible(C.collectStrings(C.callArgs(e)))) return next(e);
    // A failed hook must never let a send through (spec 6.3).
    return { deny: "betterterms: the send check failed; the draft was not sent" };
  });

  on("ui.render", { component: "AbovePrompt" }, async ($, e, next) => {
    if (e.props?.hasSurvey) return next(e);
    const snap = await scanCases($).catch(() => A.EMPTY_SNAP);
    const counts = {
      held: C.heldTotal(snap.cases),
      pending: C.pendingWithoutHeld(snap.cases),
      // A case counts as replied only while its last turn is inbound;
      // an answer in another channel clears it without waiting a tick.
      repliers: [...replied].filter((id) =>
        snap.cases.some((c) => c.id === id && c.lastDir === "in")),
    };
    const el = $.ui.resolve(e);
    return bandTree(el, counts, () => paneActions($, snap).openTab(2)) ?? next(e);
  });

  on("ui.render", { component: "Pane", requestId: PANE_ID }, async ($, e) => {
    const el = $.ui.resolve(e);
    const snap = await scanCases($).catch(() => A.EMPTY_SNAP);
    const view = { tab: await getTab($), selected: await getSelected($), editing: A.getEditing() };
    return paneTree(el, snap, view, paneActions($, snap));
  });

  on("ui.render", { component: "ToolUse" }, async ($, e, next) => {
    const row = gateRow(e.props ?? {});
    if (row === null) return next(e);
    const { Text } = $.ui.resolve(e);
    return h(Text, { color: row.color }, row.text);
  });
}
