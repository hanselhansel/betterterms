// File-format readers for the betterterms mod: mini-YAML, thread.md
// entries and ledger.jsonl. Pure functions, data in and out, so
// `node --test` can exercise them without the engine.
//
// The YAML reader is deliberately small. It covers what the mod reads:
// the block-style mappings yaml.dump writes (`key: scalar`, `key:` plus
// `- item` lists or one indented mapping level, single-quoted multiline
// scalars) plus `|`/`>` blocks and `[a, b]` / `{k: v}` flow for hand
// edits. btlib's vendored PyYAML stays the parser of record; anything
// this reader cannot shape it simply skips.

const CASE_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
const KEY_RE = /^([A-Za-z0-9_.-]+):(.*)$/;
const ENTRY_RE = /^##\s+(in|out)\s+(\S+)\s+approved_by_user:\s*(yes|no)/;

function scalar(raw) {
  const s = raw.replace(/\s+#.*$/, "").trim();
  if (s === "" || s === "null" || s === "~") return null;
  if (/^(true|false)$/i.test(s)) return s.toLowerCase() === "true";
  if (/^-?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(s)) return Number(s);
  if (s.startsWith("'")) return singleQuoted(s);
  if (s.startsWith('"')) return doubleQuoted(s);
  if (s.startsWith("[") && s.endsWith("]")) return splitFlow(s.slice(1, -1)).map(scalar);
  if (s.startsWith("{") && s.endsWith("}")) {
    const out = {};
    for (const part of splitFlow(s.slice(1, -1))) {
      const m = KEY_RE.exec(part.trim());
      if (m) out[m[1]] = scalar(m[2]);
    }
    return out;
  }
  return s;
}

// `''` inside a single-quoted scalar is a literal quote.
function singleQuoted(s) {
  let out = "";
  for (let i = 1; i < s.length; i++) {
    const ch = s[i];
    if (ch === "'") {
      if (s[i + 1] === "'") { out += "'"; i++; continue; }
      return out;
    }
    out += ch;
  }
  return out;
}

function doubleQuoted(s) {
  let out = "";
  for (let i = 1; i < s.length; i++) {
    const ch = s[i];
    if (ch === '"') return out;
    if (ch === "\\" && i + 1 < s.length) {
      const n = s[++i];
      out += n === "n" ? "\n" : n === "t" ? "\t" : n === "0" ? "\0" : n;
      continue;
    }
    out += ch;
  }
  return out;
}

// YAML line folding for quoted and `>` scalars: a break run of one
// newline folds to a space; a run of n keeps n - 1 newlines.
function foldLines(s) {
  return s.replace(/\n(?:[ \t]*\n)*[ \t]*/g, (m) => {
    const n = (m.match(/\n/g) || []).length;
    return n === 1 ? " " : "\n".repeat(n - 1);
  });
}

function splitFlow(s) {
  const parts = [];
  let depth = 0, quote = null, cur = "";
  for (const ch of s) {
    if (quote) {
      cur += ch;
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === "'" || ch === '"') quote = ch;
    else if (ch === "[" || ch === "{") depth++;
    else if (ch === "]" || ch === "}") depth--;
    if (ch === "," && depth === 0 && !quote) { parts.push(cur); cur = ""; continue; }
    cur += ch;
  }
  if (cur.trim()) parts.push(cur);
  return parts.map((p) => p.trim()).filter((p) => p !== "");
}

function indentOf(line) {
  const m = /^( *)/.exec(line);
  return m ? m[1].length : 0;
}

// Collect the lines under `key:` (indented more than the key, or `- `
// items at the key's indent) and shape them: a list, a nested mapping
// or null. Returns {value, next}.
function blockValue(lines, i, rest) {
  const base = indentOf(lines[i]);
  if (rest !== "") return inlineValue(lines, i, rest);
  const take = [];
  let j = i + 1;
  while (j < lines.length) {
    const line = lines[j];
    if (line.trim() === "") { take.push(line); j++; continue; }
    if (/^\s*#/.test(line)) { j++; continue; }
    if (indentOf(line) > base) { take.push(line); j++; continue; }
    if (/^-\s?/.test(line) && indentOf(line) === base) { take.push(line); j++; continue; }
    break;
  }
  while (take.length && take[take.length - 1].trim() === "") take.pop();
  if (!take.length) return { value: null, next: j };
  const first = take.find((l) => l.trim() !== "") ?? "";
  if (/^-\s?/.test(first)) {
    const items = [];
    for (const line of take) {
      if (line.trim() === "" || /^\s*#/.test(line)) continue;
      const m = /^-\s?(.*)$/.exec(line.trimStart());
      if (m) items.push(itemValue(m[1]));
    }
    return { value: items, next: j };
  }
  const nested = {};
  for (const line of take) {
    const m = KEY_RE.exec(line.trim());
    if (m) nested[m[1]] = scalar(m[2].trim());
  }
  return { value: nested, next: j };
}

function itemValue(item) {
  const m = KEY_RE.exec(item);
  if (m && m[1].length > 1) return { [m[1]]: scalar(m[2].trim()) };
  return scalar(item);
}

// `key: <scalar>`, `key: |`/`>` blocks and quoted scalars that PyYAML
// wraps over several lines. Returns {value, next}.
function inlineValue(lines, i, rest) {
  const trimmed = rest.trim();
  if (/^[|>][+-]?$/.test(trimmed)) {
    const style = trimmed[0];
    const base = indentOf(lines[i]);
    const body = [];
    let j = i + 1;
    while (j < lines.length && (lines[j].trim() === "" || indentOf(lines[j]) > base)) {
      body.push(lines[j]);
      j++;
    }
    let cut = 0;
    for (const line of body) if (line.trim() !== "") { cut = indentOf(line); break; }
    const stripped = body.map((l) => (l.trim() === "" ? "" : l.slice(Math.min(cut, l.length))));
    while (stripped.length && stripped[0] === "") stripped.shift();
    const text = style === "|" ? stripped.join("\n") : foldLines(stripped.join("\n"));
    if (trimmed[1] === "+") return { value: stripped.join("\n") + "\n", next: j };
    return { value: trimmed[1] === "-" ? text.replace(/\n+$/, "") : text.replace(/\n*$/, "\n"), next: j };
  }
  if (trimmed.startsWith("'") || trimmed.startsWith('"')) {
    const q = trimmed[0];
    let acc = trimmed;
    let j = i;
    while (!closedQuote(acc.slice(1), q) && j + 1 < lines.length) {
      j++;
      acc += "\n" + lines[j];
    }
    const read = q === "'" ? singleQuoted : doubleQuoted;
    return { value: foldLines(read(acc)), next: j + 1 };
  }
  return { value: scalar(trimmed), next: i + 1 };
}

// True when `s` holds an unescaped closing quote (`''` pairs inside a
// single-quoted scalar do not close it).
function closedQuote(s, q) {
  for (let i = 0; i < s.length; i++) {
    if (s[i] === q) {
      if (q === "'" && s[i + 1] === "'") { i++; continue; }
      if (q === '"') {
        let back = 0;
        for (let k = i - 1; k >= 0 && s[k] === "\\"; k--) back++;
        if (back % 2 === 1) continue;
      }
      return true;
    }
  }
  return false;
}

export function parseFlatYaml(text) {
  const out = {};
  try {
    const lines = String(text ?? "").split(/\r?\n/);
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (line.trim() === "" || /^\s*#/.test(line) || /^[-{]/.test(line.trim())) { i++; continue; }
      const m = KEY_RE.exec(line);
      if (!m || indentOf(line) > 0) { i++; continue; }
      const block = blockValue(lines, i, m[2].trimEnd());
      out[m[1]] = block.value;
      i = block.next;
    }
  } catch {
    return {};
  }
  return out;
}

export function parseThread(text) {
  const entries = [];
  for (const line of String(text ?? "").split(/\r?\n/)) {
    const m = ENTRY_RE.exec(line);
    if (m) {
      entries.push({ dir: m[1], stamp: m[2], approved: m[3] === "yes", snippet: "" });
      continue;
    }
    const cur = entries[entries.length - 1];
    if (cur && !cur.snippet && line.trim() !== "") cur.snippet = line.trim().slice(0, 80);
  }
  return entries;
}

// saved stays a per-currency map: USD and EUR never sum into one
// figure (finding 12). A record without a currency counts as USD,
// matching bt.py ledger add's default.
export function parseLedger(text) {
  const closed = new Set();
  const saved = {};
  for (const line of String(text ?? "").split(/\r?\n/)) {
    const s = line.trim();
    if (!s) continue;
    let rec;
    try { rec = JSON.parse(s); } catch { continue; }
    if (rec && typeof rec === "object") {
      if (typeof rec.case_id === "string") closed.add(rec.case_id);
      const v = Number(rec.saved_per_year);
      if (Number.isFinite(v)) {
        const cur = typeof rec.currency === "string" && rec.currency !== ""
          ? rec.currency : "USD";
        saved[cur] = (saved[cur] ?? 0) + v;
      }
    }
  }
  return { closed, saved };
}

export function safeCaseId(name) {
  return CASE_ID_RE.test(String(name ?? ""));
}

export function normalize(s) {
  return String(s ?? "").replace(/\s+/g, " ").trim();
}

// All string leaves of a value, so a send is found whether it rides in
// Bash's `command`, an MCP tool's `body` or an agent prompt.
export function collectStrings(value, out = []) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) for (const v of value) collectStrings(v, out);
  else if (value && typeof value === "object") {
    for (const v of Object.values(value)) collectStrings(v, out);
  }
  return out;
}
