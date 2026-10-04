// Wiring moved out of register.js: every hook's work, expressed over
// the `host` facade register.js builds from `$` (hostOf). The strict
// audit follows `$` only into the hooks module's own functions, so
// the facade is the one legal way for this file to reach the engine:
// it sees plain methods, never `$`. Tree building stays in ui/*; the
// host-taking helpers behind a facade live here and in lib/hostio.js.

import * as C from "./cases.js";
import * as A from "./approvals.js";
import * as IO from "./hostio.js";
import * as T from "../ui/terms.js";
import * as V from "../ui/savings.js";
import { scanCases as scan } from "./scan.js";

const PANE_ID = "betterterms";
const POLL_MS = 3000;

// Poll baselines: inbound keys already toasted, cases awaiting a
// reply, and the last print/status so redraws fire only on change.
const seen = new Map();
const replied = new Set();
let lastPrint = "";
let lastStatus = "";

// The case scan lives in lib/scan.js behind stat-fingerprint caching;
// `burst` reuses the snapshot inside a redraw storm.
export const scanCases = scan;

// A write whose path resolves inside a case dir is bookkeeping, not a
// send; the resolve stops a link under cases/ masquerading as one.
export async function isCaseWrite(host, snap, e) {
  const fp = e.file_path ?? e.path ?? e.notebook_path;
  if (typeof fp !== "string" || snap.resolvedRoot == null) return false;
  let real = (await IO.statIf(host, fp, { resolve: true }))?.realPath;
  if (real === undefined) {
    const idx = fp.lastIndexOf("/");
    if (idx <= 0) return false;
    const parent = await IO.statIf(host, fp.slice(0, idx), { resolve: true });
    if (parent?.realPath === undefined) return false;
    real = `${parent.realPath}${fp.slice(idx)}`;
  }
  return real === snap.resolvedRoot || real.startsWith(`${snap.resolvedRoot}/`);
}

async function runGate(host, snap, c, approved) {
  const dir = `${snap.root}/${c.id}`;
  const bt = await IO.findBt(host);
  if (bt === null) return { result: "error", reasons: ["bt.py not found beside the mod; install the betterterms plugin"] };
  const inbound = await host.fsExists(`${dir}/inbound.yaml`);
  const proc = await IO.runProc(host, snap.home, C.gateArgv(bt, dir, c.id, { inbound, approved }));
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

async function runHeld(host, snap, verb, caseId, hash) {
  const bt = await IO.findBt(host);
  if (bt === null) return { ok: false, error: "bt.py not found; install the betterterms plugin" };
  const h8 = A.hash8(hash);
  if (h8 === null) return { ok: false, error: "the held draft carries no hash" };
  const proc = await IO.runProc(host, snap.home, ["python3", bt, "held", verb, caseId, h8]);
  if (proc.error) return { ok: false, error: proc.error };
  let out = null;
  try { out = JSON.parse(proc.stdout); } catch { /* stderr carries it */ }
  if (proc.exitCode !== 0 || out?.ok !== true) {
    return { ok: false, error: String(out?.error ?? proc.stderr ?? `exit ${proc.exitCode}`).slice(0, 200) };
  }
  return { ok: true, hash: typeof out.hash === "string" ? out.hash : hash };
}

export async function getTab(host) {
  const { value } = await host.stateTab().catch(() => ({ value: undefined }));
  return value === 2 || value === 3 ? value : 1;
}

export async function getSelected(host) {
  const { value } = await host.stateSelected().catch(() => ({ value: undefined }));
  return typeof value === "string" ? value : null;
}

// Record the press: the full hash goes into $.state.approvals. This is
// the only writer; nothing else may mint an approval.
async function markApproved(host, hash) {
  const { value } = await host.stateApprovals().catch(() => ({ value: undefined }));
  await host.setApprovals({ ...(value ?? {}), [hash]: true });
}

// True once per approval: the entry is removed as it is read, so a
// second send of the same text is held again. A write that did not
// land (version drift, a throw) is not a take: fail closed.
async function takeApproval(host, hash) {
  const { value, version } =
    await host.stateApprovals().catch(() => ({ value: undefined, version: 0 }));
  if (value == null || typeof value !== "object" || value[hash] !== true) return false;
  const next = { ...value };
  delete next[hash];
  const res = await host.setApprovals(next, { ifVersion: version })
    .catch(() => undefined);
  return res != null && res.isSet !== false;
}

// The pane's Button/Input handlers; the gate's hash check covers a
// stale snapshot. The terms actions delegate to ui/terms.js, which
// owns the editor's state.
export function paneActions(host, snap) {
  return {
    openTab: async (n) => {
      await host.setTab(n === 2 || n === 3 ? n : 1);
      await host.openPane({ id: PANE_ID, title: "betterterms", focus: true }).catch(() => {});
    },
    select: async (id) => {
      const cur = await getSelected(host);
      await host.setSelected(cur === id ? null : id);
      host.invalidate("ui.render");
    },
    approve: async (c, held) => {
      const res = await runHeld(host, snap, "approve", c.id, held.hash);
      if (!res.ok) return host.toast(`betterterms: approve failed: ${res.error}`);
      await markApproved(host, res.hash);
      // A failed submit still leaves the approval recorded; the user
      // can resend the draft by hand and the hash check carries it.
      await host.submit({ text: A.approvePromptText(res.hash, c.id) }).catch(() =>
        host.toast(`betterterms: approved ${A.hash8(res.hash)}; resend the draft`));
    },
    reject: async (c, held) => {
      const res = await runHeld(host, snap, "reject", c.id, held.hash);
      if (!res.ok) return host.toast(`betterterms: reject failed: ${res.error}`);
      host.toast(`betterterms: draft ${A.hash8(held.hash)} rejected`);
      host.invalidate("ui.render");
    },
    edit: (held) => {
      A.setEditing(held.hash);
      host.invalidate("ui.render");
    },
    saveEdit: async (c, held, text) => {
      A.setEditing(null);
      await host.fsWrite(`${snap.root}/${c.id}/draft.yaml`, A.draftYaml(c, held, text)).catch(() => {});
      await runGate(host, snap, c, false);
      host.invalidate("ui.render");
    },
    openTerms: (c) => T.openTerms(host, snap, c),
    setTerm: (handle, raw) => T.setTermField(host, handle, raw),
    nudge: (delta) => T.nudgeField(host, delta),
    cycleFocus: () => T.cycleFocus(host),
    toggleRange: () => T.toggleRange(host),
    saveTerms: () => T.saveTerms(host),
    closeTerms: () => T.closeTerms(host),
    savingsData: () => V.savingsData(host, snap),
  };
}

// The pre-send guard. The gate re-runs on the draft as it sits on
// disk, the call is checked against the freshly rendered text, and a
// held draft passes only on an unused approval: the $.state press, or
// a marker a typed `bt approve` left, re-armed when an agent-side
// `gate --approved` already spent it.
export async function gateSend(host, snap, c, e, next) {
  const gate = await runGate(host, snap, c, false);
  const verdict = C.decideSend(gate, c);
  if (verdict.kind === "deny") {
    host.toast(`betterterms: draft for ${c.id} blocked by the gate`);
    return { deny: `betterterms gate: ${verdict.reason}` };
  }
  if (C.normalize(c.rendered ?? "") !== C.normalize(gate.rendered ?? "")) {
    return { deny: "betterterms: draft.yaml changed since this text was gated; re-run the gate" };
  }
  const shape = C.sendShapeError(C.callArgs(e), gate.rendered);
  if (shape !== null) return { deny: `betterterms: ${shape}` };
  if (verdict.kind === "held") {
    const hash = verdict.hash;
    if (hash === null) {
      host.invalidate("ui.render");
      return { deny: A.heldDenyText(null) };
    }
    const dir = `${snap.root}/${c.id}`;
    const marker = `${dir}/held/${hash}.approved`;
    let pressed = await takeApproval(host, hash);
    if (!pressed && await host.fsExists(marker).catch(() => false)) {
      // A typed `bt approve` (the prompt hook, or a manual
      // `bt.py held approve`) left the marker; adopt it as the press.
      await markApproved(host, hash);
      pressed = await takeApproval(host, hash);
    }
    if (!pressed) {
      host.invalidate("ui.render");
      return { deny: A.heldDenyText(hash) };
    }
    // The press proved consent; if an agent-side `gate --approved`
    // already spent the marker, the mod re-arms it so the resend
    // cannot deadlock on a file the agent was never meant to manage.
    if (!(await host.fsExists(marker).catch(() => false))) {
      const armed = await runHeld(host, snap, "approve", c.id, hash);
      if (!armed.ok) {
        return { deny: `betterterms: approval could not be restored: ${armed.error}` };
      }
    }
    const again = await runGate(host, snap, c, true);
    if (again.result !== "pass") {
      return { deny: `betterterms gate: ${(again.reasons ?? []).join("; ") || "not pass after approval"}` };
    }
    host.notice(e.tool_use_id, "betterterms: approved, gate pass");
    host.toast(`betterterms: draft for ${c.id} sent`);
    return next(e);
  }
  if (verdict.kind === "allow") {
    host.notice(e.tool_use_id, "betterterms: gate pass");
    host.toast(`betterterms: draft for ${c.id} sent`);
    return next(e);
  }
  const answer = await host.ask(verdict.question, { options: ["Send", "Hold"], header: "betterterms" })
    .catch(() => null);
  if (answer !== "Send") return { deny: "betterterms: send held; not approved" };
  host.notice(e.tool_use_id, "betterterms: approved, gate pass");
  return next(e);
}

export async function tick(host) {
  const snap = await scanCases(host);
  for (const c of snap.cases) {
    const s = seen.get(c.id) ?? seen.set(c.id, new Set()).get(c.id);
    const fresh = C.newInbound(c.entries, s);
    if (fresh.length > 0) {
      for (const f of fresh) s.add(C.entryKey(f));
      host.toast(C.toastText(c.id, fresh.length));
      replied.add(c.id);
    }
    // Once the agent answers, the case drops out of the band's reply bit.
    if (c.lastDir === "out") replied.delete(c.id);
  }
  const status = A.statusText(snap.cases.length, snap.saved);
  if (snap.home !== null && status !== lastStatus) {
    lastStatus = status;
    host.status(status);
  }
  const print = JSON.stringify(snap.cases.map((c) => [
    c.id, c.stage, c.pending, c.needsApproval,
    (c.held ?? []).map((held) => held.hash.slice(0, 8)).join(","),
  ]));
  if (print !== lastPrint) {
    lastPrint = print;
    host.invalidate("ui.render");
  }
}

// session.start reseeds the poll baselines so a reload does not toast
// twice, registers the command, opens the pane and starts the poll.
export async function sessionStart(host, e, next) {
  const spec = (name, description) =>
    host.registerCommand({ name, description }).catch(() => {});
  await spec("betterterms", "Open the betterterms cockpit");
  await spec("betterterms-cases", "Open the betterterms cockpit (case list)");
  const snap = await scanCases(host).catch(() => A.EMPTY_SNAP);
  seen.clear();
  replied.clear();
  for (const c of snap.cases) {
    seen.set(c.id, new Set(c.entries.filter((x) => x.dir === "in").map(C.entryKey)));
    if (c.lastDir === "in") replied.add(c.id);
  }
  if (snap.cases.length > 0) {
    void host.openPane({ id: PANE_ID, title: "betterterms" }).catch(() => {});
  }
  lastPrint = "";
  lastStatus = "";
  if (snap.home !== null) {
    lastStatus = A.statusText(snap.cases.length, snap.saved);
    host.status(lastStatus);
  }
  host.every(POLL_MS, () => tick(host).catch(() => {}));
  return next(e);
}

// Cases whose last entry is still inbound: the band's reply count.
export function repliedCases(snap) {
  return [...replied].filter((id) =>
    snap.cases.some((c) => c.id === id && c.lastDir === "in"));
}

export async function runCommand(host) {
  const opened = await host.openPane({ id: PANE_ID, title: "betterterms", focus: true })
    .catch(() => ({ isPlaced: false }));
  return {
    text: opened.isPlaced
      ? "betterterms: cockpit shown."
      : "betterterms: the pane waits for a wider terminal.",
  };
}
