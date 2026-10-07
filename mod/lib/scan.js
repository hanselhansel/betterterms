// The case-folder scan, cached on stat fingerprints. A case's parsed
// form is reused while the files it was derived from are unchanged --
// inode, mtime and size move on every atomic replace -- and the ledger
// parses once per fingerprint instead of once per call. Held/ and
// sources/ fingerprint on their entry names and kinds: a held .yaml
// never mutates after its single atomic write, so a name appearing or
// vanishing (a marker written, a record spent) is the only change. A
// case whose held list could not be read -- bt.py missing or the call
// failing -- is never cached: caching an empty held list would hide
// real drafts until some other file happened to move. A short burst
// window lets ui.render reuse the whole snapshot so a redraw or drag
// storm stats the tree once, not once per frame.
//
// The module holds $-free state; register.js resets it per session.

import * as C from "./cases.js";
import * as A from "./approvals.js";
import * as IO from "./hostio.js";

export const BURST_MS = 250;

let burstSnap = null;
let burstAt = 0;
let ledgerCache = { fp: null, parsed: null };
const caseCache = new Map(); // dir -> {fp, c}

export function resetScan() {
  burstSnap = null;
  burstAt = 0;
  ledgerCache = { fp: null, parsed: null };
  caseCache.clear();
}

// "ino:mtimeMs:size" per path, joined. Missing files fingerprint as
// "x". The inode is first because atomic replace (temp + rename, the
// only way case files are written) always moves it, even when a test
// or a fast rewrite leaves mtime and size equal.
async function fileFp(host, dir, names) {
  const st = await Promise.all(
    names.map((n) => IO.statIf(host, `${dir}/${n}`))
  );
  return st
    .map((s) => `${s?.ino ?? "x"}:${s?.mtimeMs ?? "x"}:${s?.size ?? "x"}`)
    .join("|");
}

async function namesFp(host, dir) {
  return (await IO.listIf(host, dir))
    .map((e) => `${e.name}:${e.kind}`)
    .sort()
    .join(",");
}

// Held drafts for one case, via `bt.py held list`: the CLI reports
// only records whose stored fields hash back to the filename, so a
// corrupt or tampered held file never reaches a card. Records from
// before tuple-bound names list with `legacy: true`; the mod never
// counts them. null -- not an empty list -- answers any failure, so
// the caller knows not to cache the miss.
async function heldForCase(host, home, bt, id) {
  if (bt === null) return null;
  const proc = await IO.runProc(host, home, ["python3", bt, "held", "list", id]);
  if (proc.error) return null;
  let out;
  try { out = JSON.parse(proc.stdout); } catch { return null; }
  if (!Array.isArray(out?.held)) return null;
  return out.held
    .filter((h) => h?.legacy !== true)
    .map((h) => ({
      hash: typeof h?.hash === "string" ? h.hash : "",
      rendered: typeof h?.rendered === "string" ? h.rendered : "",
      reasons: Array.isArray(h?.reasons) ? h.reasons.map(String) : [],
      heldAt: typeof h?.held_at === "string" ? h.held_at : "",
      approved: h?.approved === true,
      // The send tuple rides with the record so the card shows the
      // exact action/amount/period and an edit rebuilds draft.yaml
      // from what the owner approved, never a stale draft file.
      action: typeof h?.action === "string" ? h.action : null,
      offer: typeof h?.offer === "number" ? h.offer : null,
      period: typeof h?.period === "string" ? h.period : null,
      currency: typeof h?.currency === "string" ? h.currency : null,
      inbound: typeof h?.inbound === "string" ? h.inbound : null,
    }))
    .filter((h) => h.hash !== "");
}

const WATCHED = ["brief.yaml", "plan.yaml", "draft.yaml", "gate.json", "thread.md"];

async function scanCase(host, home, bt, dir, name, ledger) {
  const [fp, heldFp, sourcesFp] = await Promise.all([
    fileFp(host, dir, WATCHED),
    namesFp(host, `${dir}/held`),
    namesFp(host, `${dir}/sources`),
  ]);
  // The ledger's closed bit rides inside the key: a close entry must
  // re-derive stage/next/pending, not patch the cached row.
  const full = `${fp};held:${heldFp};src:${sourcesFp};closed:${ledger.closed.has(name)}`;
  const hit = caseCache.get(dir);
  if (hit?.fp === full) {
    return { ...hit.c };
  }
  const read = (n) => IO.readIf(host, `${dir}/${n}`);
  const [briefText, planText, draftText, gateText, threadText] =
    await Promise.all(WATCHED.map(read));
  const held = heldFp === ""
    ? []
    : await heldForCase(host, home, bt, name);
  const c = C.deriveCase({
    id: name,
    briefText, threadText, draftText, gateText, planText,
    draftMtimeMs: fpPart(fp, 2),
    gateMtimeMs: fpPart(fp, 3),
    threadMtimeMs: fpPart(fp, 4),
    sourceCount: sourcesFp === "" ? 0 : sourcesFp.split(",").length,
    closed: ledger.closed.has(name),
    held: held ?? [],
  });
  // A held answer that could not be computed -- bt.py missing or the
  // list call failing -- is not cacheable: the next scan must try
  // again rather than freeze an empty pane.
  if (bt !== null && held !== null) caseCache.set(dir, { fp: full, c });
  return c;
}

// The mtime of one "ino:mtimeMs:size" segment of a fingerprint.
function fpPart(fp, i) {
  const m = fp.split("|")[i]?.split(":")[1];
  const n = Number(m);
  return Number.isFinite(n) ? n : 0;
}

// The case-folder snapshot every hook draws from: brief, plan (the
// offer bar's targets), thread, draft, gate.json, held/, ledger.
// .floor is not scanned here; the terms editor reads it at `t`
// only to show the user (ui/terms.js).
export async function scanCases(host, { burst = false } = {}) {
  if (
    burst && burstSnap !== null && Date.now() - burstAt < BURST_MS
  ) {
    return burstSnap;
  }
  const home = await IO.homeDir(host);
  if (home === null) return A.EMPTY_SNAP;
  const ledgerPath = `${home}/ledger.jsonl`;
  const ledgerFp = await fileFp(host, home, ["ledger.jsonl"]);
  if (ledgerCache.fp !== ledgerFp) {
    ledgerCache = {
      fp: ledgerFp,
      parsed: C.parseLedger((await IO.readIf(host, ledgerPath)) ?? ""),
    };
  }
  const ledger = ledgerCache.parsed;
  const root = `${home}/cases`;
  const rootStat = await IO.statIf(host, root);
  if (rootStat?.kind !== "dir") {
    return { home, root, cases: [], saved: ledger.saved, savedOnce: ledger.once };
  }
  const bt = await IO.findBt(host);
  const cases = await Promise.all(
    (await IO.listIf(host, root))
      .filter((ent) => ent.kind === "dir" && !ent.isLink && C.safeCaseId(ent.name))
      .map((ent) => scanCase(host, home, bt, `${root}/${ent.name}`, ent.name, ledger))
  );
  const snap = {
    home, root,
    cases, saved: ledger.saved, savedOnce: ledger.once,
  };
  burstSnap = snap;
  burstAt = Date.now();
  return snap;
}
