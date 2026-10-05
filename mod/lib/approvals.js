// Pure approval-flow helpers for the betterterms mod: the approve
// prompt wording, the status line and the draft.yaml rewrite for
// Edit. The $.state references live in register.js: the audit needs
// each ref's plugin and key spelled as literals in the file that
// calls $.state. Everything that touches `$` (fs reads, bt.py
// subprocesses, presses) lives in register.js and lib/wiring.js: the
// hooks-module audit follows `$` only into functions declared in
// register.js, never across an import.
//
// The approval contract (spec 6.3, amended by decision 0020): the
// Approve press writes the hash-bound marker through
// `bt.py held approve`, and the submitted prompt sends the agent
// through `bt.py gate --approved` exactly once. The marker is the
// only consent the gate spends, in every mode.

export const GATE_TIMEOUT_MS = 30000;
export const EMPTY_SNAP = { home: null, root: null, cases: [], saved: {}, savedOnce: {} };

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

// One-time savings stay out of the per-year figure: "$100 once ·
// EUR 50 once", or "" when the ledger has none.
export function onceText(once) {
  return Object.keys(once ?? {})
    .map((k) => `${money(k, once[k])} once`)
    .join(" · ");
}

// The card in edit mode, by held hash, plus the text a failed save
// keeps in the editor: a redraw after a failed write must not drop
// the user's typing. Module scope: UI-local state, not approval
// state; renders read them as view.editing / view.editText and the
// Edit/Save handlers change them then invalidate.
let editing = null;
let editText = null;
export function getEditing() { return editing; }
export function getEditText() { return editText; }
export function setEditing(hash, text = null) {
  editing = hash;
  editText = text;
}

export function hash8(hash) {
  if (typeof hash !== "string" || hash === "") return null;
  return hash.slice(0, 8);
}

// POSIX single-quote escaping, like shlex.quote: a token of shell-safe
// characters prints bare; anything else wraps in single quotes with an
// embedded ' written '"'"'. A home path with a space must word-split
// back to one argv element when the printed command is run.
const SH_SAFE = /^[A-Za-z0-9_@%+=:,./-]+$/;
export function shQuote(s) {
  const str = String(s);
  if (SH_SAFE.test(str)) return str;
  return `'${str.replace(/'/g, `'"'"'`)}'`;
}
const shJoin = (argv) => argv.map(shQuote).join(" ");

// The prompt the press submits: the marker is armed, so one
// `gate --approved` run spends it and returns the rendered text,
// which is then sent verbatim as its own argument. `argv` is the
// full command the mod itself would run (C.gateArgv plus
// --approved): the resolved absolute bt.py path and the case's own
// draft path, so the instruction runs as printed.
export function approvePromptText(hash, caseId, argv) {
  return `betterterms: the user approved draft ${hash8(hash)} for ${caseId}. ` +
    `Run \`${shJoin(argv)}\` exactly once, then send the ` +
    "returned rendered text verbatim as its own argument, nothing added.";
}

// The toast when the prompt could not be submitted: the marker is
// armed but the agent never saw the instruction, so it carries the
// same runnable command.
export function approveFallbackText(hash, caseId, argv) {
  return `betterterms: approved ${hash8(hash)} for ${caseId}, but the ` +
    `prompt did not send. Run \`${shJoin(argv)}\` once, then send ` +
    "the returned rendered text verbatim as its own argument.";
}

export function statusText(nCases, saved, once) {
  const base = `bt: ${nCases} case${nCases === 1 ? "" : "s"} · ${savedText(saved)} saved`;
  const o = onceText(once);
  return o === "" ? base : `${base} · ${o}`;
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
