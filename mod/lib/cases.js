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
export const SEND_MIN_CHARS = 24;
// Gate results that leave a draft sendable (pending autonomy and the
// user's yes). The band counts these; block and error do not.
export const GATE_SENDABLE = new Set(["pass", "needs_approval"]);
const AUTONOMY_DEFAULT = { act: 2, coach: 1 };

function numOr(v, dflt) {
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}

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

// One case's display row and send-detection inputs.
// raw: { id, briefText, threadText, draftText, gateText, planText,
//        held, draftMtimeMs, gateMtimeMs, threadMtimeMs, sourceCount,
//        closed }
export function deriveCase(raw) {
  const brief = parseFlatYaml(raw.briefText);
  const draft = raw.draftText ? parseFlatYaml(raw.draftText) : null;
  const gate = parseGate(raw.gateText);
  const entries = parseThreadAll(raw.threadText);
  const mode = brief.mode === "coach" ? "coach" : "act";
  const autonomy = numOr(brief.autonomy, AUTONOMY_DEFAULT[mode] ?? 2);
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
    autonomy,
    stage,
    action,
    draft,
    gateResult: gate?.result ?? null,
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

// The open case whose last rendered gate text the call carries, else
// null. A closed case's leftover gate.json can never match a send.
export function findSend(strings, cases) {
  for (const c of cases) {
    if (c.stage === "closed") continue;
    const d = normalize(c.rendered ?? "");
    if (d === "") continue;
    for (const s of strings) {
      const p = normalize(s);
      if (!p.includes(d)) continue;
      if (d.length >= SEND_MIN_CHARS || p.includes(c.id)) return c;
    }
  }
  return null;
}

export function gateArgv(btPath, dir, id, opts = {}) {
  const argv = ["python3", btPath, "gate", id, "--draft", `${dir}/draft.yaml`];
  if (opts.inbound) argv.push("--inbound", `${dir}/inbound.yaml`);
  if (opts.approved) argv.push("--approved");
  return argv;
}

// gate: {result, reasons, hash?}. Returns {kind: deny|ask|allow|held}.
// needs_approval never asks inline: the draft is already held on disk
// (held/<hash>.yaml) and the only way through is the pane's Approve,
// which the send guard recognizes by the hash in $.state.
export function decideSend(gate, c) {
  if (!gate || (gate.result !== "pass" && gate.result !== "needs_approval")) {
    const why = gate?.reasons?.length ? gate.reasons.join("; ") : "the gate could not run";
    return { kind: "deny", reason: why };
  }
  if (gate.result === "needs_approval") {
    return { kind: "held", hash: typeof gate.hash === "string" ? gate.hash : null };
  }
  if (c.autonomy <= 1) {
    return { kind: "deny", reason: `autonomy ${c.autonomy}: the user sends, the agent drafts` };
  }
  if (c.autonomy === 2) {
    return { kind: "ask", reapprove: false, question: `Send the drafted message for ${c.id}?` };
  }
  return { kind: "allow" };
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

// Total held drafts across cases (the Approvals badge).
export function heldTotal(cases) {
  return cases.reduce((n, c) => n + (c.held?.length ?? 0), 0);
}

// Cases whose saved verdict leaves a send pending and whose held files
// do not already cover that rendered text, so the band does not count
// one draft twice.
export function pendingWithoutHeld(cases) {
  return cases.filter((c) => {
    if (!c.pending) return false;
    const want = normalize(c.rendered ?? "");
    return !(c.held ?? []).some((h) => normalize(h.rendered ?? "") === want);
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

// The tool.call event minus its envelope fields: what is left is the
// tool's own arguments, which is what collectStrings should search.
export function callArgs(e) {
  const { tool, tool_use_id, consent, agentId, ...args } = e ?? {};
  return args;
}

// Envelope fields a send call may carry beside the message body:
// where the message goes, never what it says.
const ENVELOPE_KEYS = new Set([
  "to", "cc", "bcc", "from", "sender", "subject", "title",
  "recipient", "recipients", "channel", "channel_id", "chat_id",
  "thread", "thread_id", "conversation_id", "message_id",
  "in_reply_to", "reply_to", "email", "address", "phone", "number",
  "user", "username", "target", "destination", "room",
]);

// (key, value) for every string leaf: the send-shape check needs the
// field names, not just the texts.
export function collectPairs(value, key = "", out = []) {
  if (typeof value === "string") out.push({ key, value });
  else if (Array.isArray(value)) {
    for (const v of value) collectPairs(v, key, out);
  } else if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) collectPairs(v, k, out);
  }
  return out;
}

// null when the call is a clean send of the gated text: exactly one
// argument equals the freshly rendered message verbatim, and every
// other string argument is an envelope field. The rendered text inside
// a longer argument, a second prose field, or no verbatim carrier at
// all is a send the gate never saw and the user never approved.
export function sendShapeError(args, rendered) {
  const r = normalize(rendered);
  if (r === "") return "the gate produced no text to send";
  let exact = 0;
  for (const p of collectPairs(args)) {
    const v = normalize(p.value);
    if (v === r) {
      exact += 1;
      continue;
    }
    if (v.includes(r)) {
      return "the gated text must be the whole argument, not part of a longer one";
    }
    if (v !== "" && !ENVELOPE_KEYS.has(String(p.key).toLowerCase())) {
      return `argument '${p.key}' carries text the gate never saw`;
    }
  }
  if (exact === 0) return "no argument carries the gated text verbatim";
  if (exact > 1) return "the gated text fills more than one argument";
  return null;
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
