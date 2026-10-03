// betterterms-mod: the opt-in Claude Code mod for betterterms.
//
// A function-hook plugin: hooks/hooks.json names this file (modules are
// resolved relative to hooks/, hence "../register.js") and the engine
// calls register(on) once at load. Four surfaces:
//
//   session.start: registers /betterterms-cases, opens the pipeline pane
//     when cases exist, baselines inbound thread entries, starts a 3s
//     poll that toasts on new inbound turns.
//   tool.call: the pre-send guard. A call whose arguments carry a case's
//     draft text is treated as a send from that case and gated through
//     `python3 bt.py gate`. Block -> { deny }. Pass -> the autonomy in
//     brief.yaml decides: 1 refuses (the user sends), 2 asks each time,
//     3 and 4 send inside the approved plan. needs_approval (an
//     irreversible action) always asks, then re-gates with --approved.
//   ui.render: a Pane with the case pipeline and an AbovePrompt band
//     counting drafts waiting for approval.
//   command.run: /betterterms-cases reopens the pane.
//
// The mod reads only $BETTERTERMS_HOME/cases/<id>/{brief.yaml,thread.md,
// draft.yaml,inbound.yaml existence}, sources/ listings, and
// ledger.jsonl. It writes nothing and stores nothing off the session.
//
// `seen` and `lastPrint` are module scope because the loader requires $
// to reach only top-level declared functions. session.start reseeds
// both, so a reload re-baselines instead of double-toasting.

import * as C from "./lib/cases.js";

const PANE_ID = "betterterms";
const COMMAND = "betterterms-cases";
const POLL_MS = 3000;
const GATE_TIMEOUT_MS = 30000;
const EMPTY_SNAP = { home: null, root: null, resolvedRoot: null, cases: [], savedPerYear: 0 };

const seen = new Map();
let lastPrint = "";

async function homeDir($) {
  const env = await $.env.get("BETTERTERMS_HOME");
  if (env !== undefined && env !== "") return env;
  const home = await $.env.get("HOME");
  if (home === undefined || home === "") return null;
  return `${home}/.betterterms`;
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

async function scanCases($) {
  const home = await homeDir($);
  if (home === null) return EMPTY_SNAP;
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
    const [briefText, threadText, draftText, draftSt, threadSt, sources] = await Promise.all([
      readIf($, `${dir}/brief.yaml`),
      readIf($, `${dir}/thread.md`),
      readIf($, `${dir}/draft.yaml`),
      statIf($, `${dir}/draft.yaml`),
      statIf($, `${dir}/thread.md`),
      listIf($, `${dir}/sources`),
    ]);
    cases.push(C.deriveCase({
      id: ent.name,
      briefText,
      threadText,
      draftText,
      draftMtimeMs: draftSt?.mtimeMs ?? 0,
      threadMtimeMs: threadSt?.mtimeMs ?? 0,
      sourceCount: sources.length,
      closed: ledger.closed.has(ent.name),
    }));
  }
  return { home, root, resolvedRoot: rootStat.realPath ?? root, cases, savedPerYear: ledger.savedPerYear };
}

// True when the call writes inside a case dir: drafting, scoring and
// logging are bookkeeping, not sends. Paths are resolved before the
// comparison so a link under cases/ cannot masquerade as bookkeeping.
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

async function runGate($, snap, c, approved) {
  const dir = `${snap.root}/${c.id}`;
  let bt = null;
  for (const p of C.btPaths($.plugin.root)) {
    if (await $.fs.exists(p)) { bt = p; break; }
  }
  if (bt === null) {
    return { result: "error", reasons: ["bt.py not found beside the mod; install the betterterms plugin too"] };
  }
  const inbound = await $.fs.exists(`${dir}/inbound.yaml`);
  const env = snap.home === null ? undefined : { BETTERTERMS_HOME: snap.home };
  let proc;
  try {
    proc = await $.process.run(C.gateArgv(bt, dir, c.id, { inbound, approved }), {
      env, timeoutMs: GATE_TIMEOUT_MS,
    });
  } catch (err) {
    return { result: "error", reasons: [`gate run failed: ${String(err?.message ?? err).slice(0, 200)}`] };
  }
  try {
    const out = JSON.parse(proc.stdout);
    return {
      result: typeof out.result === "string" ? out.result : "error",
      reasons: Array.isArray(out.reasons) ? out.reasons.map(String) : [],
    };
  } catch {
    return { result: "error", reasons: [(proc.stderr || `gate exit ${proc.exitCode}`).slice(0, 200)] };
  }
}

async function gateSend($, snap, c, e, next) {
  const gate = await runGate($, snap, c, false);
  const verdict = C.decideSend(gate, c);
  if (verdict.kind === "deny") return { deny: `betterterms gate: ${verdict.reason}` };
  if (verdict.kind === "allow") {
    $.ui.notice(e.tool_use_id, "betterterms: gate pass");
    return next(e);
  }
  const answer = await $.ui.ask(verdict.question, { options: ["Send", "Hold"], header: "betterterms" })
    .catch(() => null);
  if (answer !== "Send") return { deny: "betterterms: send held; not approved" };
  if (!verdict.reapprove) {
    $.ui.notice(e.tool_use_id, "betterterms: approved, gate pass");
    return next(e);
  }
  const again = await runGate($, snap, c, true);
  if (again.result !== "pass") {
    return { deny: `betterterms gate: ${again.reasons.join("; ") || "not pass after approval"}` };
  }
  $.ui.notice(e.tool_use_id, "betterterms: approved");
  return next(e);
}

async function tick($) {
  const snap = await scanCases($);
  for (const c of snap.cases) {
    let s = seen.get(c.id);
    if (!s) { s = new Set(); seen.set(c.id, s); }
    const fresh = C.newInbound(c.entries, s);
    if (fresh.length > 0) {
      for (const f of fresh) s.add(C.entryKey(f));
      $.ui.toast(C.toastText(c.id, fresh.length));
    }
  }
  const print = JSON.stringify(snap.cases.map((c) => [c.id, c.stage, c.needsApproval]));
  if (print !== lastPrint) {
    lastPrint = print;
    $.ui.invalidate("ui.render");
  }
}

export function register(on) {
  on("session.start", async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: "Show the betterterms case pipeline",
    }).catch(() => {});
    const snap = await scanCases($).catch(() => EMPTY_SNAP);
    seen.clear();
    for (const c of snap.cases) {
      seen.set(c.id, new Set(c.entries.filter((x) => x.dir === "in").map(C.entryKey)));
    }
    if (snap.cases.length > 0) {
      void $.ui.open({ id: PANE_ID, title: "betterterms" }).catch(() => {});
    }
    lastPrint = "";
    $.clock.every(POLL_MS, () => tick($).catch(() => {}));
    return next(e);
  });

  on("command.run", { command: COMMAND }, async ($) => {
    const opened = await $.ui.open({ id: PANE_ID, title: "betterterms" }).catch(() => ({ isPlaced: false }));
    return {
      text: opened.isPlaced
        ? "betterterms: case pipeline shown."
        : "betterterms: the pane waits for a wider terminal.",
    };
  });

  on("tool.call", async ($, e, next) => {
    // The agent's own approval question is not a send; gating it would
    // put our ask in front of its ask.
    if (e.tool === "AskUserQuestion") return next(e);
    const { tool, tool_use_id, consent, agentId, ...args } = e;
    const strings = C.collectStrings(args);
    const plausible = strings.some(
      (s) => s.length >= C.SEND_MIN_CHARS || /-\d{8}-/.test(s),
    );
    if (!plausible) return next(e);
    let snap;
    try {
      snap = await scanCases($);
    } catch {
      return next(e);
    }
    if (snap.cases.length === 0) return next(e);
    if (await isCaseWrite($, snap, e)) return next(e);
    const hit = C.findSend(strings, snap.cases);
    if (hit === null) return next(e);
    return gateSend($, snap, hit, e, next);
  });

  on("ui.render", { component: "AbovePrompt" }, async ($, e, next) => {
    if (e.props?.hasSurvey) return next(e);
    const snap = await scanCases($).catch(() => EMPTY_SNAP);
    const n = C.pendingCount(snap.cases);
    if (n === 0) return next(e);
    const { Box, Text } = $.ui.resolve(e);
    return h(Box, null, h(Text, { dimColor: true }, C.bandText(n)));
  });

  on("ui.render", { component: "Pane", requestId: PANE_ID }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e);
    const snap = await scanCases($).catch(() => EMPTY_SNAP);
    const room = Math.max(1, (e.viewport?.rows ?? 24) - 4);
    const rows = C.paneRows(snap.cases, snap.savedPerYear).slice(0, room);
    return h(
      Box,
      { flexDirection: "column" },
      ...rows.map((r) => h(Text, { dimColor: r.dim }, r.text)),
    );
  });
}
