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

// The last gate verdict the exchange skill saved to the case folder as
// gate.json: {result, reasons, rendered}, or null when absent or
// malformed. rendered is the exact text the agent must send; null on
// block.
export function parseGate(text) {
  try {
    const g = JSON.parse(text);
    if (!g || typeof g !== "object" || typeof g.result !== "string") return null;
    return {
      result: g.result,
      reasons: Array.isArray(g.reasons) ? g.reasons.map(String) : [],
      rendered: typeof g.rendered === "string" && g.rendered !== "" ? g.rendered : null,
    };
  } catch { return null; }
}

// One case's display row and send-detection inputs.
// raw: { id, briefText, threadText, draftText, gateText, draftMtimeMs,
//        gateMtimeMs, threadMtimeMs, sourceCount, closed }
export function deriveCase(raw) {
  const brief = parseFlatYaml(raw.briefText);
  const draft = raw.draftText ? parseFlatYaml(raw.draftText) : null;
  const gate = parseGate(raw.gateText);
  const entries = parseThread(raw.threadText);
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
    gateResult: gate?.result ?? null,
    rendered: gate?.rendered ?? null,
    draftUnsent,
    gated,
    pending,
    needsApproval: pending && gate.result === "needs_approval",
    entryCount: entries.length,
    lastDir: last?.dir ?? null,
    entries,
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

// gate: {result, reasons}. Returns {kind: deny|ask|allow, ...}.
export function decideSend(gate, c) {
  if (!gate || (gate.result !== "pass" && gate.result !== "needs_approval")) {
    const why = gate?.reasons?.length ? gate.reasons.join("; ") : "the gate could not run";
    return { kind: "deny", reason: why };
  }
  if (gate.result === "needs_approval") {
    return {
      kind: "ask",
      reapprove: true,
      question: `${c.action ?? "send"} on ${c.id} needs approval. Send it?`,
    };
  }
  if (c.autonomy <= 1) {
    return { kind: "deny", reason: `autonomy ${c.autonomy}: the user sends, the agent drafts` };
  }
  if (c.autonomy === 2) {
    return { kind: "ask", reapprove: false, question: `Send the drafted message for ${c.id}?` };
  }
  return { kind: "allow" };
}

export function bandText(n) {
  return `${n} draft${n === 1 ? "" : "s"} waiting to send`;
}

export function toastText(id, n) {
  return n === 1 ? `New reply in ${id}.` : `${n} new replies in ${id}.`;
}

// bt.py lives in the core plugin's skill tree. From the installed mod
// that is a sibling plugin dir; run in place from the repo it is the
// repo's skills/ dir. Both candidates are tried in order.
export function btPaths(root) {
  return [
    `${root}/../betterterms/skills/betterterms-guardrails/scripts/bt.py`,
    `${root}/../skills/betterterms-guardrails/scripts/bt.py`,
  ];
}

// Rows the pane draws: a header, one row per case, a totals footer.
export function paneRows(cases, savedPerYear) {
  const rows = [{ text: "case".padEnd(28) + "stage".padEnd(12) + "next", dim: true }];
  for (const c of cases) {
    const stage = c.stage === "exchange" ? "in exchange" : c.stage;
    rows.push({
      text: c.id.padEnd(28).slice(0, 28) + stage.padEnd(12).slice(0, 12) + c.next,
      dim: c.stage === "closed",
    });
  }
  if (savedPerYear > 0) rows.push({ text: `saved $${Math.round(savedPerYear)}/yr`, dim: true });
  if (cases.length === 0) rows.push({ text: "no cases yet", dim: true });
  return rows;
}

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
