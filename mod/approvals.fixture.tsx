// Shared fake world for the engine-side tests run by
// `claude plugin test ./mod` (approvals.test.tsx, surfaces.test.tsx).
// Named .tsx on purpose, like register.test.tsx: `node --test`
// discovers .test.ts and .test.js but leaves .tsx alone, and plain
// node cannot resolve `claude-code/testing`.
//
// The kit loads this plugin itself. `on` answers the op events the mod
// calls: env, fs, state, process.run (bt.py), prompt.submit and the ui
// surface calls; tool.call answers as the real call underneath.

export const ID = 'bills-20261003-a1b2';
export const DIR = `/bt/cases/${ID}`;
export const HASH = 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890';
export const HASH8 = HASH.slice(0, 8);
export const HASH2 = '9999991234567890abcdef1234567890abcdef1234567890abcdef1234567890';
export const RENDERED = 'I can pay $1,000 a year for this plan.';
export const BRIEF = 'pack: bills\nmode: act\nautonomy: 4\n';
export const DRAFT = `action: send\noffer: 1000\ntemplate: 'I can pay {offer} a year for this plan.'\nclaims: []\n`;
export const THREAD = `# thread ${ID}\n## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;
export const GATE_HELD = JSON.stringify({
  result: 'needs_approval',
  reasons: ["action 'cancel' requires --approved"],
  rendered: RENDERED,
  hash: HASH,
});
export const HELD_YAML =
  `hash: ${HASH}\n` +
  `rendered: '${RENDERED}'\n` +
  'reasons:\n- action \'cancel\' requires --approved\n' +
  'held_at: 2026-10-04T12:00:00+00:00\n';
export const HELD_REC = {
  hash: HASH, rendered: RENDERED,
  reasons: ["action 'cancel' requires --approved"],
  held_at: '2026-10-04T12:00:00+00:00',
};
export const LEDGER = '{"case_id":"x-20260101-aaaa","saved_per_year":1440,"currency":"USD"}\n';

export type Files = Record<string, string>;
export type Dirs = Record<string, unknown[]>;
export type HeldRec = { hash: string; rendered: string; reasons: string[]; held_at: string };
export type OpHook = (event: string, hook: (...a: never[]) => unknown) => unknown;

export interface Wired {
  files: Files;
  dirs: Dirs;
  held: HeldRec[];
  state: Map<string, { value: unknown; version: number }>;
  prompts: string[];
  statuses: string[];
  toasts: string[];
  opens: string[];
  runs: string[][];
  // gate text for a plain run; approvedText for `gate --approved`.
  gateText: () => string;
  approvedText: () => string;
  openPlaced: boolean;
}

export function fixtureFiles(extra: Files = {}): Files {
  return {
    [`${DIR}/brief.yaml`]: BRIEF,
    [`${DIR}/thread.md`]: THREAD,
    [`${DIR}/draft.yaml`]: DRAFT,
    [`${DIR}/gate.json`]: GATE_HELD,
    [`${DIR}/held/${HASH}.yaml`]: HELD_YAML,
    '/bt/ledger.jsonl': LEDGER,
    ...extra,
  };
}

export function fixtureDirs(): Dirs {
  return {
    '/bt/cases': [{ name: ID, kind: 'dir', isLink: false }],
    [`${DIR}/sources`]: [],
    [`${DIR}/held`]: [{ name: `${HASH}.yaml`, kind: 'file', isLink: false }],
  };
}

// Answers every op event the mod raises. The `next` half of each event
// is the result the mod's `$.` call resolves to.
export function wire(on: OpHook, w: Wired) {
  on('env.get', (_$: never, e: { name: string }) => ({
    value: e.name === 'BETTERTERMS_HOME' ? '/bt' : '/u',
  }));
  on('fs.read', (_$: never, e: { path: string }) =>
    e.path in w.files ? { value: w.files[e.path] } : { deny: 'ENOENT' });
  on('fs.list', (_$: never, e: { path: string }) => ({ value: w.dirs[e.path] ?? [] }));
  on('fs.exists', (_$: never, e: { path: string }) => ({
    value: e.path in w.files || e.path in w.dirs || e.path.endsWith('scripts/bt.py'),
  }));
  on('fs.stat', (_$: never, e: { path: string }) =>
    e.path in w.files || e.path in w.dirs
      ? { value: { kind: e.path in w.dirs ? 'dir' : 'file', size: 1, mtimeMs: 2, isLink: false } }
      : { deny: 'ENOENT' });
  on('fs.write', (_$: never, e: { path: string; value: string }) => {
    w.files[e.path] = e.value;
    return { value: undefined };
  });
  on('state.get', (_$: never, e: { plugin: string; key: string }) => {
    const cur = w.state.get(`${e.plugin}/${e.key}`);
    return { value: { value: cur?.value, version: cur?.version ?? 0 } };
  });
  on('state.set', (_$: never, e: { plugin: string; key: string; value: unknown; ifVersion?: number }) => {
    const k = `${e.plugin}/${e.key}`;
    const cur = w.state.get(k);
    if (e.ifVersion !== undefined && e.ifVersion !== (cur?.version ?? 0))
      return { value: { isSet: false, version: cur?.version ?? 0 } };
    const version = (cur?.version ?? 0) + 1;
    w.state.set(k, { value: e.value, version });
    return { value: { isSet: true, version } };
  });
  on('process.run', (_$: never, e: { argv: string[] }) => processRun(w, e.argv));
  on('prompt.submit', (_$: never, e: { text: string }) => {
    w.prompts.push(e.text);
    return { text: e.text };
  });
  on('ui.open', (_$: never, e: { id: string }) => {
    w.opens.push(e.id);
    return { value: w.openPlaced ? { isPlaced: true } : { isPlaced: false, reason: 'narrow' } };
  });
  on('ui.status', (_$: never, e: { text?: string }) => { w.statuses.push(e.text ?? ''); return { value: undefined }; });
  on('ui.toast', (_$: never, e: { text: string }) => { w.toasts.push(e.text); return { value: undefined }; });
  on('ui.invalidate', () => ({ value: undefined }));
  on('command.register', () => ({ value: {} }));
  on('clock.every', () => ({ value: undefined }));
  on('session.start', (_$: never, e: { cwd: string }) => ({ cwd: e.cwd }));
  on('tool.call', (_$: never, e: { tool: string }) => ({ result: { ran: e.tool } }));
}

// The fake bt.py, exported so a test can play the agent's own
// process calls (a `gate --approved` the submitted prompt asks for).
export function processRun(w: Wired, argvIn: string[]) {
  const argv = argvIn.map(String);
  w.runs.push(argv);
  const heldDir = `${DIR}/held`;
  if (argv[2] === 'held' && argv[3] === 'list') {
    const held = w.held.map((r) => ({
      ...r,
      approved: `${heldDir}/${r.hash}.approved` in w.files,
    }));
    return { value: { exitCode: 0, stdout: JSON.stringify({ held }), stderr: '' } };
  }
  if (argv[2] === 'held' && (argv[3] === 'approve' || argv[3] === 'reject' || argv[3] === 'drop')) {
    const h8 = String(argv[5] ?? '');
    const hits = w.held.filter((r) => r.hash.startsWith(h8));
    if (hits.length !== 1)
      return { value: { exitCode: 2, stdout: `{"error":"no held draft matching ${h8}"}`, stderr: '' } };
    const h = hits[0].hash;
    if (argv[3] === 'approve') {
      w.files[`${heldDir}/${h}.approved`] = `hash: ${h}\n`;
      (w.dirs[heldDir] as unknown[]).push({ name: `${h}.approved`, kind: 'file', isLink: false });
    } else {
      // reject and drop both remove the record and marker; drop
      // writes no thread.md marker (this fake does not model one).
      w.held = w.held.filter((r) => r.hash !== h);
      delete w.files[`${heldDir}/${h}.yaml`];
      delete w.files[`${heldDir}/${h}.approved`];
      w.dirs[heldDir] = (w.dirs[heldDir] as { name: string }[])
        .filter((e) => e.name !== `${h}.yaml` && e.name !== `${h}.approved`);
    }
    return { value: { exitCode: 0, stdout: `{"ok":true,"hash":"${h}"}`, stderr: '' } };
  }
  if (argv[2] === 'gate' && argv.includes('--approved')) {
    // Like the real CLI: --approved passes only on a live marker,
    // and the marker plus its record are spent on use; the held
    // dir entry goes with them so a rescan sees the spend.
    let hash: string | undefined;
    try { hash = JSON.parse(w.gateText()).hash; } catch { hash = undefined; }
    const marker = hash ? `${heldDir}/${hash}.approved` : '';
    if (hash !== undefined && marker in w.files) {
      delete w.files[marker];
      delete w.files[`${heldDir}/${hash}.yaml`];
      w.held = w.held.filter((r) => r.hash !== hash);
      w.dirs[heldDir] = (w.dirs[heldDir] as { name: string }[])
        .filter((e) => e.name !== `${hash}.yaml` && e.name !== `${hash}.approved`);
      const pass = w.approvedText();
      w.files[`${DIR}/gate.json`] = pass;
      return { value: { exitCode: 0, stdout: pass, stderr: '' } };
    }
  }
  const stdout = w.gateText();
  const code = stdout.includes('"needs_approval"') ? 3 : stdout.includes('"block"') ? 1 : 0;
  // The real gate writes its verdict to gate.json on every call.
  if (argv[2] === 'gate') w.files[`${DIR}/gate.json`] = stdout;
  return { value: { exitCode: code, stdout, stderr: '' } };
}

export function fresh(over: Partial<Wired> = {}): Wired {
  return {
    files: fixtureFiles(),
    dirs: fixtureDirs(),
    held: [{ ...HELD_REC }],
    state: new Map(),
    prompts: [],
    statuses: [],
    toasts: [],
    opens: [],
    runs: [],
    gateText: () => GATE_HELD,
    // A real pass verdict carries rendered (and hash only on
    // needs_approval): without rendered the next scan would read
    // gate.json as carrying no text to match.
    approvedText: () => JSON.stringify({ result: 'pass', reasons: [], rendered: RENDERED }),
    openPlaced: true,
    ...over,
  };
}

export const PANE_PROPS = {
  title: 'betterterms', isFocused: true, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 30 }, view: {},
};

export const BAND_PROPS = {
  hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 120,
  scroll: { offset: 0, bodyRows: 5 }, view: {},
};
