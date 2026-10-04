// Pure approval-flow helpers for the betterterms mod: the
// held/<hash>.yaml reader, the deny/submit/status wordings and the
// draft.yaml rewrite for Edit. The $.state references live in
// register.js: the audit needs each ref's plugin and key spelled as
// literals in the file that calls $.state. Everything that
// touches `$` (fs reads, bt.py subprocesses, state writes, presses)
// lives in register.js: the hooks-module audit follows `$` only into
// functions declared in that file, never across an import.
//
// The approval invariant (spec 6.3): a send held by the gate is denied
// with the pane's name, never asked inline; a press records the full
// SHA-256 in $.state.approvals and submits the resend prompt; the
// resend re-runs `bt.py gate --approved`, which consumes the on-disk
// approval file once. $.state is the only witness an agent cannot
// forge, so an approval file alone never lets a send through.

import { parseFlatYaml } from "./cases.js";

export const GATE_TIMEOUT_MS = 30000;
export const EMPTY_SNAP = { home: null, root: null, resolvedRoot: null, cases: [], savedPerYear: 0 };

const HASH64 = /^[0-9a-f]{64}$/;

// The card in edit mode, by held hash. Module scope: it is UI-local
// state, not approval state; renders read it as view.editing and the
// Edit/Save handlers change it then invalidate.
let editing = null;
export function getEditing() { return editing; }
export function setEditing(hash) { editing = hash; }

export function hash8(hash) {
  if (typeof hash !== "string" || hash === "") return null;
  return hash.slice(0, 8);
}

// One held/<hash>.yaml: {hash, rendered, reasons, held_at}. The reader
// tolerates junk (a file mid-write, a dropped note) as "not held".
export function parseHeldFile(text) {
  const y = parseFlatYaml(text);
  if (!y || !HASH64.test(String(y.hash ?? ""))) return null;
  if (typeof y.rendered !== "string" || y.rendered === "") return null;
  return {
    hash: String(y.hash),
    rendered: y.rendered,
    reasons: Array.isArray(y.reasons) ? y.reasons.map(String) : [],
    heldAt: typeof y.held_at === "string" ? y.held_at : "",
  };
}

export function heldDenyText(hash) {
  const h8 = hash8(hash);
  return h8 === null
    ? "betterterms: held for your approval in the BetterTerms pane."
    : `betterterms: held for your approval in the BetterTerms pane (draft ${h8}).`;
}

export function approvePromptText(hash, caseId) {
  return `betterterms: the user approved draft ${hash8(hash)} for ${caseId}. ` +
    "Send it now with the same text.";
}

export function statusText(nCases, savedPerYear) {
  return `bt: ${nCases} case${nCases === 1 ? "" : "s"} · $${Math.round(savedPerYear)}/yr saved`;
}

// draft.yaml rewritten with the edited message as the template. The
// draft's own keys (action, offer, period, claims) are kept so the
// gate sees the same draft shape; the template goes out as a literal
// block so the text is byte-exact.
export function draftYaml(c, held, text) {
  const d = c.draft && typeof c.draft === "object" ? { ...c.draft } : {};
  d.template = null;
  const lines = [];
  for (const [k, v] of Object.entries(d)) {
    if (k === "template" || v === undefined) continue;
    lines.push(`${k}: ${yamlScalar(v)}`);
  }
  lines.push("template: |-");
  for (const l of String(text ?? "").split("\n")) lines.push(`  ${l}`);
  return lines.join("\n") + "\n";
}

function yamlScalar(v) {
  if (v === null || v === undefined) return "null";
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return `[${v.map(yamlScalar).join(", ")}]`;
  if (typeof v === "object") {
    const inner = Object.entries(v).map(([k, x]) => `${k}: ${yamlScalar(x)}`).join(", ");
    return `{${inner}}`;
  }
  const s = String(v);
  return /[:#\[\]{},&*!|>'"%@`]|^\s|\s$/.test(s) ? `'${s.replace(/'/g, "''")}'` : s;
}
