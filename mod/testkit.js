// Shared fixtures and the fake engine for the mod's node:test suites.
// Not a hooks module: never imported by register.js, only by the
// *.test.js files, though it ships inside the plugin dir.

import assert from "node:assert/strict";

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
text: 'I can pay $1,000 a year for this plan.

  If that works, say the word and I will set it up.'
claims:
- f1
`;

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
// The second btPath candidate register.js probes: plugin root /p/mod +
// ../skills resolves to this literal string in the fake fs.
export const BT = "/p/mod/../skills/betterterms-guardrails/scripts/bt.py";

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
  const env = opts.env ?? { BETTERTERMS_HOME: HOME };
  const files = opts.files ?? {};
  const dirs = opts.dirs ?? {};
  const calls = { run: [], toast: [], open: [], ask: [], notice: [], invalidate: [], register: [], every: [] };
  const $ = {
    env: { get: async (n) => env[n] },
    fs: {
      read: async (p) => {
        if (p in files) return files[p];
        throw new Error(`ENOENT ${p}`);
      },
      exists: async (p) => p in files || p in dirs,
      list: async (p) => {
        if (p in dirs) return dirs[p];
        throw new Error(`ENOENT ${p}`);
      },
      stat: async (p, init) => {
        const st = (opts.stats ?? {})[p];
        if (p in files)
          return { kind: "file", size: files[p].length, mtimeMs: st?.mtimeMs ?? 1, isLink: false, realPath: st?.realPath ?? p };
        if (p in dirs)
          return { kind: "dir", size: 0, mtimeMs: st?.mtimeMs ?? 1, isLink: false, realPath: st?.realPath ?? p };
        throw new Error(`ENOENT ${p}`);
      },
    },
    process: {
      run: async (argv, init) => {
        calls.run.push({ argv, init });
        return opts.gate ?? { exitCode: 0, stdout: '{"result":"pass","reasons":[]}', stderr: "" };
      },
    },
    ui: {
      resolve: () => ({ Box: "Box", Text: "Text" }),
      toast: (t) => calls.toast.push(t),
      open: async (req) => { calls.open.push(req); return { isPlaced: true }; },
      notice: (id, t) => calls.notice.push({ id, text: t }),
      ask: async (q, init) => { calls.ask.push({ q, init }); return opts.answer ?? "Hold"; },
      invalidate: (w) => calls.invalidate.push(w),
      status: () => {},
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
  return { $, calls };
}

export function fakeOn() {
  const hooks = [];
  const on = (event, ...rest) => {
    const hook = rest[rest.length - 1];
    const matcher = rest.length > 1 ? rest[0] : undefined;
    hooks.push({ event, matcher, hook });
    return { catch() {} };
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
