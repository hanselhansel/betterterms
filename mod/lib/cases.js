// Case-state decisions for the betterterms mod, built on the readers
// in lib/parse.js. Pure functions only: register.js feeds them strings
// read through `$.fs` from the allowed paths, and `node --test` covers
// them without the engine.

import {
  collectStrings, normalize, parseFlatYaml, parseLedger, parseThread,
  safeCaseId,
} from "./parse.js";

export {
  collectStrings, normalize, parseFlatYaml, parseLedger, parseThread,
  safeCaseId,
};

export const STAGES = ["found", "researched", "exchange", "waiting", "closed"];
// Gate results that leave a draft sendable pending the user's yes.
// The band counts these; block and error do not.
export const GATE_SENDABLE = new Set(["pass", "needs_approval"]);

// The last gate verdict bt.py wrote into the case folder as gate.json:
// {result, reasons, rendered, hash?}, or null when absent or malformed.
// rendered is the exact text the agent must send; null on block.
export function parseGate(text) {
  try {
    const g = JSON.parse(text);
    if (!g || typeof g !== "object" || typeof g.result !== "string") return null;
    return {
      result: g.result,
      reasons: Array.isArray(g.reasons) ? g.reasons.map(String) : [],
      rendered: typeof g.rendered === "string" && g.rendered !== "" ? g.rendered : null,
      hash: typeof g.hash === "string" ? g.hash : null,
    };
  } catch { return null; }
}

// thread.md entries plus the `## rejected <time> <hash>` markers
// `bt.py held reject` appends. A rejected line is a marker, not a turn:
// it must not enter the entries list or become the previous entry's
// snippet, so it is stripped here before the entry parser runs.
export function parseThreadAll(text) {
  const clean = String(text ?? "")
    .split(/\r?\n/)
    .filter((l) => !/^##\s+rejected\s/.test(l))
    .join("\n");
  return parseThread(clean);
}

// One case's display row.
// raw: { id, briefText, threadText, draftText, gateText, planText,
//        held, draftMtimeMs, gateMtimeMs, threadMtimeMs, sourceCount,
//        closed }
export function deriveCase(raw) {
  const brief = parseFlatYaml(raw.briefText);
  const draft = raw.draftText ? parseFlatYaml(raw.draftText) : null;
  const gate = parseGate(raw.gateText);
  const entries = parseThreadAll(raw.threadText);
  const mode = brief.mode === "coach" ? "coach" : "act";
  const action = draft?.action != null ? String(draft.action) : null;
  const last = entries[entries.length - 1];
  const draftUnsent = draft != null && (raw.draftMtimeMs ?? 0) > (raw.threadMtimeMs ?? 0);
  // The saved verdict describes the current draft only when the gate
  // ran at or after the draft's last write.
  const gated = gate != null
    && GATE_SENDABLE.has(gate.result)
    && (raw.gateMtimeMs ?? 0) >= (raw.draftMtimeMs ?? 0);
  let stage;
  if (raw.closed) stage = "closed";
  else if (last?.dir === "out") stage = "waiting";
  else if (entries.length > 0) stage = "exchange";
  else if ((raw.sourceCount ?? 0) > 0) stage = "researched";
  else stage = "found";
  const pending = gated && draftUnsent && stage !== "closed";
  const c = {
    id: raw.id,
    pack: String(brief.pack ?? raw.id.replace(/-\d{8}-[0-9a-f]{4}$/, "")),
    mode,
    stage,
    action,
    draft,
    gateResult: gate?.result ?? null,
    gateHash: gate?.hash ?? null,
    rendered: gate?.rendered ?? null,
    draftUnsent,
    gated,
    pending,
    needsApproval: pending && gate.result === "needs_approval",
    entryCount: entries.length,
    lastDir: last?.dir ?? null,
    lastSnippet: last?.snippet ?? "",
    entries,
    held: Array.isArray(raw.held) ? raw.held : [],
    offer: offerMarks(raw.planText),
  };
  c.next = nextAction(c);
  return c;
}

export function nextAction(c) {
  switch (c.stage) {
    case "closed": return "closed";
    case "waiting": return "await their reply";
    case "found": return "finish intake";
    case "researched": return "draft the first message";
    default:
      if (!c.draftUnsent) return "draft the reply";
      if (!c.gated) return "gate the draft";
      return c.needsApproval ? "approve the draft" : "send the draft";
  }
}

export function pendingCount(cases) {
  return cases.filter((c) => c.pending).length;
}

export function gateArgv(btPath, dir, id, opts = {}) {
  const argv = ["python3", btPath, "gate", id, "--draft", `${dir}/draft.yaml`];
  if (opts.inbound) argv.push("--inbound", `${dir}/inbound.yaml`);
  return argv;
}

// The AbovePrompt band's one line: fresh replies first, then how many
// drafts wait (held files plus gate-passed unsent ones). Empty string
// draws nothing.
export function bandText(held, pending, repliers = []) {
  const parts = [];
  if (repliers.length > 0) parts.push(`${repliers.join(", ")} replied`);
  const n = held + pending;
  if (n > 0) parts.push(`${n} draft${n === 1 ? "" : "s"} waiting`);
  return parts.join(", ");
}

// Total current held drafts across cases (the Approvals badge). Only
// the record the last gate verdict held counts: a hash that is not
// the case's gate.json hash is superseded and shown greyed.
export function heldTotal(cases) {
  return cases.reduce(
    (n, c) =>
      n + (c.held ?? []).filter((h) => h.hash === c.gateHash).length,
    0,
  );
}

// Cases whose saved verdict leaves a send pending and whose current
// held record does not already cover that rendered text, so the band
// does not count one draft twice.
export function pendingWithoutHeld(cases) {
  return cases.filter((c) => {
    if (!c.pending) return false;
    const want = normalize(c.rendered ?? "");
    return !(c.held ?? []).some(
      (h) => h.hash === c.gateHash && normalize(h.rendered ?? "") === want,
    );
  }).length;
}

// The Cases-tab detail strip: Intake > Research > Draft > Sent > Reply
// > Close with the case's step bracketed. `exchange` splits on the last
// turn's direction: an inbound last turn is a reply to work on, an
// outbound is a draft in progress.
export function progressStrip(c) {
  const steps = ["Intake", "Research", "Draft", "Sent", "Reply", "Close"];
  const at = { found: 0, researched: 1, exchange: c.lastDir === "in" ? 4 : 2, waiting: 3, closed: 5 }[c.stage] ?? 0;
  return steps.map((s, i) => (i === at ? `[${s}]` : s)).join(" > ");
}

// plan.yaml's offer anchors for the selected case's offer bar: start
// is the counterparty's first stated amount (a fact), offer their
// latest, target the plan's. Facts hold what they said; price options
// stand in when no fact is recorded. Numbers only, or null when the
// plan carries none. The walk-away never enters here: it lives in
// `.floor`, which the mod never reads.
export function offerMarks(planText) {
  const plan = parseFlatYaml(planText);
  if (!plan || Object.keys(plan).length === 0) return null;
  const amount = (v) => {
    if (v && typeof v === "object") v = v.amount ?? v.value;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : null;
  };
  const facts = (Array.isArray(plan.facts) ? plan.facts : [])
    .map((f) => amount(f))
    .filter((n) => n !== null);
  const options = (Array.isArray(plan.options) ? plan.options : [])
    .filter((o) => !o || typeof o !== "object" || (o.kind ?? "price") === "price")
    .map((o) => amount(o && (o.value ?? o.amount)))
    .filter((n) => n !== null);
  const theirs = facts.length > 0 ? facts : options;
  const target = amount(plan.target);
  const start = theirs[0] ?? null;
  const offer = theirs.length > 1 ? theirs[theirs.length - 1] : null;
  if (start === null && offer === null && target === null) return null;
  return { start, offer, target, currency: String(plan.currency ?? "USD") };
}

export function toastText(id, n) {
  return n === 1 ? `New reply in ${id}.` : `${n} new replies in ${id}.`;
}

// "." and ".." segments resolved lexically: some engine fs calls take
// the path verbatim, so candidates arrive already clean.
export function normPath(p) {
  const out = [];
  for (const seg of String(p).split("/")) {
    if (seg === "" || seg === ".") continue;
    if (seg === "..") { out.pop(); continue; }
    out.push(seg);
  }
  return `/${out.join("/")}`;
}

// bt.py lives in the core plugin's skill tree. In the repo the mod dir
// sits beside skills/, so ../skills reaches it. In a real install the
// marketplace cache lays plugins as <cache>/<market>/<plugin>/<version>
// and each plugin carries its own version dir, so the core plugin is
// two levels up under betterterms/<its version>; the caller passes the
// version dir names it found by listing, newest first.
export function btPaths(root, versions = []) {
  const rel = "skills/betterterms-guardrails/scripts/bt.py";
  return [
    ...versions.map((v) => normPath(`${root}/../../betterterms/${v}/${rel}`)),
    normPath(`${root}/../betterterms/${rel}`),
    normPath(`${root}/../${rel}`),
  ];
}

// Row builders for the pane live in ui/pane.js now.

// Entries in `entries` not yet in `seen` (a Set of `dir:stamp` keys).
// Returns the new entries; caller adds their keys once toasted.
export function newInbound(entries, seen) {
  const fresh = [];
  for (const e of entries) {
    if (e.dir !== "in") continue;
    const key = `${e.dir}:${e.stamp}`;
    if (!seen.has(key)) fresh.push(e);
  }
  return fresh;
}

export function entryKey(e) {
  return `${e.dir}:${e.stamp}`;
}
