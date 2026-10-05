// Host-facing IO primitives. The engine's `$` never leaves
// register.js: it is bound once into a `host` facade (hostOf) and
// every other module receives that plain object. These helpers are
// the shared vocabulary over it: home discovery, tolerant fs reads,
// the bt.py probe and the one process-run wrapper everything uses.
// They know paths and timeouts, never $, so `node --test` covers them
// through the same facade the engine sees.

import * as C from "./cases.js";
import * as A from "./approvals.js";

// ~/.betterterms: BETTERTERMS_HOME wins, else $HOME/.betterterms.
export async function homeDir(host) {
  const env = await host.envBtHome();
  if (env !== undefined && env !== "") return env;
  const home = await host.envHome();
  return home === undefined || home === "" ? null : `${home}/.betterterms`;
}

export async function readIf(host, path) {
  try { return await host.fsRead(path); } catch { return undefined; }
}

export async function statIf(host, path) {
  try { return await host.fsStat(path); } catch { return undefined; }
}

export async function listIf(host, path) {
  try { return await host.fsList(path); } catch { return []; }
}

// bt.py lives in the core plugin's skill tree, probed once per call.
// A resolved path is cached per plugin root but revalidated on every
// call with fsExists: an upgrade or uninstall mid-session swaps the
// file out from under the hit, and the probe then runs again. A miss
// is likewise re-probed each call: the core plugin may be installed
// while the session is live.
const btFound = new Map();

export async function findBt(host) {
  const root = host.pluginRoot;
  const hit = btFound.get(root);
  if (hit !== undefined && await host.fsExists(hit)) return hit;
  btFound.delete(root);
  const sibs = C.normPath(`${root}/../../betterterms`);
  const versions = (await listIf(host, sibs))
    .filter((e) => e.kind === "dir")
    .map((e) => String(e.name))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    .reverse();
  for (const p of C.btPaths(root, versions)) {
    if (await host.fsExists(p)) {
      btFound.set(root, p);
      return p;
    }
  }
  return null;
}

export function resetBt() {
  btFound.clear();
}

// The one process wrapper. `extra` carries init fields a caller adds;
// `case set-floor` passes {stdin: "..."} here, which is how the
// walk-away travels with argv untouched.
export async function runProc(host, home, argv, extra = {}) {
  const env = home === null || home === undefined
    ? undefined
    : { BETTERTERMS_HOME: home };
  try {
    return await host.procRun(argv, { env, timeoutMs: A.GATE_TIMEOUT_MS, ...extra });
  } catch (err) {
    return { error: String(err?.message ?? err).slice(0, 200) };
  }
}
