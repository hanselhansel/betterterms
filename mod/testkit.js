// Shared fixtures and the fake engine for the mod's node:test suites.
// Not a hooks module: never imported by register.js, only by the
// *.test.js files, though it ships inside the plugin dir.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { resetScan } from "./lib/scan.js";
import { resetBt } from "./lib/hostio.js";

// The element factory the engine injects. Hooks call it only when a
// render hook runs; tests stub it before firing those hooks.
globalThis.h = (tag, props, ...children) => ({ tag, props, children });

export const BRIEF = `pack: bills
mode: act
direction: pay
goals:
- lower the bill
priorities:
- price
- terms
ranking_check:
  passed: true
  samples: []
autonomy: 2
never_disclose:
- acct-7788
deadline: null
`;

export const DRAFT = `action: send
offer: 1000
period: year
template: 'I can pay {offer} for this plan.

  If that works, say the word and I will set it up.'
claims:
- f1
`;

// The gate verdict the exchange skill saves to gate.json: rendered is
// the template with placeholders filled, the exact text a send carries.
export const RENDERED =
  "I can pay $1,000/year for this plan.\n" +
  "If that works, say the word and I will set it up.";
export const GATE =
  `{"result":"pass","reasons":[],"rendered":${JSON.stringify(RENDERED)}}`;
export const GATE_NEEDS_APPROVAL =
  `{"result":"needs_approval","reasons":["action 'cancel' requires --approved"],` +
  `"rendered":${JSON.stringify(RENDERED)}}`;
export const GATE_BLOCK =
  '{"result":"block","reasons":["outside your limits; escalate to the user"],"rendered":null}';

export const THREAD = `# thread bills-20261003-a1b2
# one entry per turn: \`## in|out <ISO time> approved_by_user: yes|no\`
## in 2026-10-03T15:04:05+00:00 approved_by_user: no
We can do $1,100 a year.
## out 2026-10-03T15:20:00+00:00 approved_by_user: yes
I can pay $1,000 a year for this plan. If that works, say the word and I will set it up.
`;

export const LEDGER = [
  '{"case_id":"bills-20260901-aaaa","saved_per_year":240,"pack":"bills"}',
  "not json",
  '{"case_id":"offer-20260902-bbbb","saved_per_year":1200,"pack":"offers"}',
].join("\n");

export const CASE_ID = "bills-20261003-a1b2";
export const HOME = "/bt";
export const DIR = `${HOME}/cases/${CASE_ID}`;
// The bt.py path the repo layout resolves to: plugin root /p/mod +
// ../skills, normalized, lands here in the fake fs.
export const BT = "/p/skills/betterterms-guardrails/scripts/bt.py";

// The same canonical-tuple hash bt.py computes for held/<sha256>.yaml
// (action, offer in minor units, period, currency, rendered, sorted
// JSON, SHA-256). Fixtures keep ASCII so JSON.stringify matches
// json.dumps(ensure_ascii=True).
export function heldHash(r) {
  const offer = r.offer === null || r.offer === undefined
    ? null
    : (Math.round(Number(r.offer) * 100) / 100).toFixed(2);
  const canon = JSON.stringify({
    action: r.action ?? null,
    currency: r.currency ?? null,
    offer,
    period: r.period ?? null,
    rendered: r.rendered ?? null,
  });
  return createHash("sha256").update(canon, "utf8").digest("hex");
}

// A process.run responder that speaks the bt.py commands the mod
// calls. `gate` replays opts.gate (a proc result, a verdict object, or
// a fn of argv); on `--approved` a needs_approval verdict passes only
// when the marker file exists, and consumes it like the real CLI.
// `held list` answers from opts.held[id] record tuples; `held
// approve|reject` maintain the marker files in `files`.
export function btRoute(opts, files) {
  // The held records the fake CLI reports also land as files, so a
  // held/ listing (and its stat fingerprint) moves like the real fs.
  for (const [id, recs] of Object.entries(opts.held ?? {})) {
    for (const r of recs) {
      const path = `${HOME}/cases/${id}/held/${heldHash(r)}.yaml`;
      files[path] = JSON.stringify(r);
    }
  }
  const dropRecord = (id, h) => {
    delete files[`${HOME}/cases/${id}/held/${h}.yaml`];
    delete files[`${HOME}/cases/${id}/held/${h}.approved`];
  };
  const wrap = (o, code) => ({
    exitCode: code ?? (o.result === "block" ? 1 : o.result === "needs_approval" ? 3 : 0),
    stdout: JSON.stringify(o),
    stderr: "",
  });
  return (argv) => {
    if (argv[2] === "gate") {
      const g = typeof opts.gate === "function" ? opts.gate(argv) : opts.gate;
      if (g === undefined || g === null) {
        return wrap({ result: "pass", reasons: [], rendered: RENDERED });
      }
      if ("stdout" in g || "exitCode" in g) return g; // a proc result
      const id = argv[3];
      if (g.result === "needs_approval" && argv.includes("--approved")
          && typeof g.hash === "string"
          && `${HOME}/cases/${id}/held/${g.hash}.approved` in files) {
        dropRecord(id, g.hash);
        return wrap({ result: "pass", reasons: [], rendered: g.rendered });
      }
      return wrap(g);
    }
    if (argv[2] === "held" && argv[3] === "list") {
      const id = argv[4];
      const held = (opts.held?.[id] ?? []).map((r) => {
        const hash = heldHash(r);
        return {
          ...r, hash,
          approved: `${HOME}/cases/${id}/held/${hash}.approved` in files,
        };
      });
      return wrap({ held });
    }
    if (argv[2] === "held" && argv[3] === "disarm") {
      // The real `held disarm` resolves over records and markers and
      // unlinks only the .approved file.
      const id = argv[4];
      const h8 = String(argv[5] ?? "");
      const heldDir = `${HOME}/cases/${id}/held`;
      const hits = new Set(
        (opts.held?.[id] ?? [])
          .map((r) => heldHash(r))
          .filter((h) => h.startsWith(h8)),
      );
      for (const f of Object.keys(files)) {
        const m = new RegExp(`${heldDir}/([0-9a-f]{64})\\.approved$`).exec(f);
        if (m && m[1].startsWith(h8)) hits.add(m[1]);
      }
      if (hits.size !== 1) {
        return { exitCode: 2, stdout: `{"error":"no held draft matching ${h8}"}`, stderr: "" };
      }
      const h = [...hits][0];
      delete files[`${heldDir}/${h}.approved`];
      return wrap({ ok: true, hash: h });
    }
    if (argv[2] === "held" && (argv[3] === "approve" || argv[3] === "reject")) {
      const id = argv[4];
      const h8 = String(argv[5] ?? "");
      const recs = opts.held?.[id] ?? [];
      const hits = recs.map((r) => heldHash(r)).filter((h) => h.startsWith(h8));
      if (hits.length !== 1) {
        return { exitCode: 2, stdout: `{"error":"no held draft matching ${h8}"}`, stderr: "" };
      }
      const h = hits[0];
      if (argv[3] === "approve") {
        files[`${HOME}/cases/${id}/held/${h}.approved`] = `hash: ${h}\n`;
      } else {
        opts.held[id] = recs.filter((r) => heldHash(r) !== h);
        dropRecord(id, h);
      }
      return wrap({ ok: true, hash: h });
    }
    return wrap({});
  };
}

export function caseFiles(over = {}) {
  return {
    [`${DIR}/brief.yaml`]: BRIEF,
    [`${DIR}/thread.md`]: THREAD,
    "/bt/ledger.jsonl": LEDGER,
    [BT]: "#!/usr/bin/env python3\n",
    ...over,
  };
}

export function caseDirs(over = {}) {
  return {
    [`${HOME}/cases`]: [{ name: CASE_ID, kind: "dir", isLink: false }],
    [`${DIR}/sources`]: [],
    ...over,
  };
}

export function fakeDollar(opts = {}) {
  // Each fake $ is a fresh session, so the module-level scan cache
  // and the resolved-bt cache reset exactly as register() resets them
  // for the engine.
  resetScan();
  resetBt();
  const env = opts.env ?? { BETTERTERMS_HOME: HOME };
  const files = opts.files ?? {};
  const dirs = opts.dirs ?? {};
  const calls = {
    run: [], toast: [], open: [], ask: [], notice: [], invalidate: [],
    register: [], every: [], submit: [], status: [], write: [],
    read: [], stat: [], list: [],
  };
  // $.state backed by a Map; the test-facing facade reads and seeds
  // values by bare key.
  const store = new Map();
  const state = {
    get size() { return store.size; },
    get: (k) => store.get(k)?.value,
    set: (k, v) =>
      store.set(k, { value: v, version: (store.get(k)?.version ?? 0) + 1 }),
  };
  const run = opts.run ?? btRoute(opts, files);
  // mtimes move on every write, like a real fs: the scan cache's
  // fingerprints rely on it, and dir mtimes move when an entry under
  // them appears or goes (the fake counts files below the path).
  const bumps = new Map();
  const bump = (p) => bumps.set(p, (bumps.get(p) ?? 1) + 1);
  // Inodes move on every write too: the runtime saves files atomically
  // (temp + replace), so a rewrite is always a fresh inode even when
  // bytes and mtime happen to stay equal.
  const inos = new Map();
  let inoSeq = 0;
  const inoOf = (p) => {
    if (!inos.has(p)) inos.set(p, (inoSeq += 10));
    return inos.get(p);
  };
  const dirMtime = (p) =>
    (opts.stats ?? {})[p]?.mtimeMs ??
    1 + Object.keys(files).filter((f) => f.startsWith(`${p}/`)).length
      + (bumps.get(p) ?? 0);
  const $ = {
    env: { get: async (n) => env[n] },
    fs: {
      read: async (p) => {
        calls.read.push(p);
        if (p in files) return files[p];
        throw new Error(`ENOENT ${p}`);
      },
      write: async (p, text) => {
        files[p] = text;
        calls.write.push({ path: p, text });
        bump(p);
        bump(p.slice(0, p.lastIndexOf("/")));
        inos.set(p, inoOf(p) + 1);
      },
      exists: async (p) => p in files || p in dirs,
      list: async (p) => {
        calls.list.push(p);
        const ents = [...(dirs[p] ?? [])];
        const seen = new Set(ents.map((e) => e.name));
        for (const f of Object.keys(files)) {
          if (!f.startsWith(`${p}/`)) continue;
          const name = f.slice(p.length + 1);
          if (name.includes("/") || seen.has(name)) continue;
          ents.push({ name, kind: "file", isLink: false });
        }
        if (ents.length === 0 && !(p in dirs)) throw new Error(`ENOENT ${p}`);
        return ents;
      },
      stat: async (p, init) => {
        calls.stat.push(p);
        const st = (opts.stats ?? {})[p];
        if (p in files)
          return { kind: "file", size: files[p].length, mtimeMs: st?.mtimeMs ?? bumps.get(p) ?? 1, ino: st?.ino ?? inoOf(p), isLink: false, realPath: st?.realPath ?? p };
        if (p in dirs)
          return { kind: "dir", size: 0, mtimeMs: dirMtime(p), ino: st?.ino ?? inoOf(p), isLink: false, realPath: st?.realPath ?? p };
        throw new Error(`ENOENT ${p}`);
      },
    },
    process: {
      run: async (argv, init) => {
        calls.run.push({ argv, init });
        return run(argv, init);
      },
    },
    state: {
      get: async (ref) => ({
        value: store.get(ref.key)?.value,
        version: store.get(ref.key)?.version ?? 0,
      }),
      set: async (ref, value, setOpts) => {
        const cur = store.get(ref.key);
        if (setOpts?.ifVersion !== undefined && setOpts.ifVersion !== (cur?.version ?? 0))
          return { isSet: false, version: cur?.version ?? 0 };
        const version = (cur?.version ?? 0) + 1;
        store.set(ref.key, { value, version });
        return { isSet: true, version };
      },
    },
    prompt: { submit: async (e) => { calls.submit.push(e.text); return { text: e.text }; } },
    ui: {
      resolve: () => ({ Box: "Box", Text: "Text", Button: "Button", Input: "Input", Select: "Select" }),
      toast: (t) => calls.toast.push(t),
      open: async (req) => { calls.open.push(req); return { isPlaced: true }; },
      notice: (id, t) => calls.notice.push({ id, text: t }),
      ask: async (q, init) => { calls.ask.push({ q, init }); return opts.answer ?? "Hold"; },
      invalidate: (w) => calls.invalidate.push(w),
      status: (t) => calls.status.push(t),
      log: () => {},
    },
    clock: {
      now: async () => 0,
      every: (ms, fn) => { calls.every.push({ ms, fn }); return () => {}; },
      after: () => () => {},
      sleep: async () => {},
    },
    command: { register: async (spec) => { calls.register.push(spec); return {}; } },
    plugin: { name: "betterterms-mod", root: "/p/mod" },
    session: { id: "s", cwd: "/w" },
  };
  return { $, calls, state };
}

export function fakeOn() {
  const hooks = [];
  const on = (event, ...rest) => {
    const hook = rest[rest.length - 1];
    const matcher = rest.length > 1 ? rest[0] : undefined;
    const rec = { event, matcher, hook, onCatch: undefined };
    hooks.push(rec);
    return { catch(fn) { rec.onCatch = fn; } };
  };
  const get = (event, pick) => {
    const found = hooks.filter((h) => h.event === event && (!pick || pick(h)));
    assert.equal(found.length >= 1, true, `no hook for ${event}`);
    return found[0].hook;
  };
  return { on, hooks, get };
}

// A `next` that records each call and resolves to a marker.
export function fired(nextMarker = { result: "ran" }) {
  const calls = [];
  const next = async (e) => { calls.push(e); return nextMarker; };
  return { next, calls, marker: nextMarker };
}
