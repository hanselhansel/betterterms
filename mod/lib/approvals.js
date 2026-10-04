// Pure approval-flow helpers for the betterterms mod: the deny/submit
// wordings, the status line and the draft.yaml rewrite for Edit. The
// $.state references live in register.js: the audit needs each ref's
// plugin and key spelled as literals in the file that calls $.state.
// Everything that touches `$` (fs reads, bt.py subprocesses, state
// writes, presses) lives in register.js and lib/wiring.js: the
// hooks-module audit follows `$` only into functions declared in
// register.js, never across an import.
//
// The approval invariant (spec 6.3): a send held by the gate is denied
// with the pane's name, never asked inline. Consent is an unused
// $.state entry, written only by the pane press or by the mod's own
// prompt.submit hook on a typed `bt approve`; a .approved marker on
// disk never counts by itself. The marker is only what
// `bt.py gate --approved` spends: the send check re-arms it for the
// re-gate when needed, and disarms it when the re-gate does not spend
// it. The entry is spent on read; the marker is spent by the gate.

export const GATE_TIMEOUT_MS = 30000;
export const EMPTY_SNAP = { home: null, root: null, resolvedRoot: null, cases: [], saved: {} };

// "$486" for USD, "EUR 200" otherwise: only USD gets the sign.
export function money(currency, v) {
  const n = Math.round(Number(v) || 0);
  return currency === "USD" ? `$${n}` : `${currency} ${n}`;
}

// The per-currency savings figure, "$486/yr · EUR 200/yr" or "$0/yr".
export function savedText(saved) {
  const keys = Object.keys(saved ?? {});
  if (keys.length === 0) return "$0/yr";
  return keys.map((k) => `${money(k, saved[k])}/yr`).join(" · ");
}

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

export function heldDenyText(hash) {
  const h8 = hash8(hash);
  return h8 === null
    ? "betterterms: held for your approval in the BetterTerms pane."
    : `betterterms: held for your approval in the BetterTerms pane (draft ${h8}).`;
}

export function approvePromptText(hash, caseId) {
  return `betterterms: the user approved draft ${hash8(hash)} for ${caseId}. ` +
    "Send it now: the approved text verbatim as its own argument, " +
    "nothing added. The send guard re-runs the gate; do not run it yourself.";
}

export function statusText(nCases, saved) {
  return `bt: ${nCases} case${nCases === 1 ? "" : "s"} · ${savedText(saved)} saved`;
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
