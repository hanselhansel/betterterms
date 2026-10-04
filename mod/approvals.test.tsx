// Engine-side approval-flow tests for `claude plugin test ./mod`.
// Named .tsx on purpose, like register.test.tsx: `node --test`
// discovers .test.ts and .test.js but leaves .tsx alone, and plain
// node cannot resolve `claude-code/testing`.
//
// The kit loads this plugin itself. `on` answers the op events the mod
// calls: env, fs, state, process.run (bt.py), prompt.submit, the ui
// surface calls and the real tool.call beneath the guard.

import { test, expect } from 'claude-code/testing';

const ID = 'bills-20261003-a1b2';
const DIR = `/bt/cases/${ID}`;
const HASH = 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890';
const HASH8 = HASH.slice(0, 8);
const HASH2 = '9999991234567890abcdef1234567890abcdef1234567890abcdef1234567890';
const RENDERED = 'I can pay $1,000 a year for this plan.';
const BRIEF = 'pack: bills\nmode: act\nautonomy: 4\n';
const DRAFT = `action: send\noffer: 1000\ntemplate: 'I can pay {offer} a year for this plan.'\nclaims: []\n`;
const THREAD = `# thread ${ID}\n## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;
const GATE_HELD = JSON.stringify({
  result: 'needs_approval',
  reasons: ["action 'cancel' requires --approved"],
  rendered: RENDERED,
  hash: HASH,
});
const HELD_YAML =
  `hash: ${HASH}\n` +
  `rendered: '${RENDERED}'\n` +
  'reasons:\n- action \'cancel\' requires --approved\n' +
  'held_at: 2026-10-04T12:00:00+00:00\n';
const HELD_REC = {
  hash: HASH, rendered: RENDERED,
  reasons: ["action 'cancel' requires --approved"],
  held_at: '2026-10-04T12:00:00+00:00',
};
const LEDGER = '{"case_id":"x-20260101-aaaa","saved_per_year":1440,"currency":"USD"}\n';

type Files = Record<string, string>;
type Dirs = Record<string, unknown[]>;
type HeldRec = { hash: string; rendered: string; reasons: string[]; held_at: string };
type OpHook = (event: string, hook: (...a: never[]) => unknown) => unknown;

interface Wired {
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
  throwGate?: boolean;
}

function fixtureFiles(extra: Files = {}): Files {
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

function fixtureDirs(): Dirs {
  return {
    '/bt/cases': [{ name: ID, kind: 'dir', isLink: false }],
    [`${DIR}/sources`]: [],
    [`${DIR}/held`]: [{ name: `${HASH}.yaml`, kind: 'file', isLink: false }],
  };
}

// Answers every op event the mod raises. The `next` half of each event
// is the result the mod's `$.` call resolves to.
function wire(on: OpHook, w: Wired) {
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
      ? { value: { kind: e.path in w.dirs ? 'dir' : 'file', size: 1, mtimeMs: 2, isLink: false, realPath: e.path } }
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
  on('process.run', (_$: never, e: { argv: string[] }) => {
    if (w.throwGate) return { deny: 'spawn blew up' };
    const argv = e.argv.map(String);
    w.runs.push(argv);
    const heldDir = `${DIR}/held`;
    if (argv[2] === 'held' && argv[3] === 'list') {
      const held = w.held.map((r) => ({
        ...r,
        approved: `${heldDir}/${r.hash}.approved` in w.files,
      }));
      return { value: { exitCode: 0, stdout: JSON.stringify({ held }), stderr: '' } };
    }
    if (argv[2] === 'held' && argv[3] === 'disarm') {
      // The real `held disarm` resolves over records and markers and
      // unlinks only the .approved file.
      const h8 = String(argv[5] ?? '');
      const hits = new Set(w.held.filter((r) => r.hash.startsWith(h8)).map((r) => r.hash));
      for (const f of Object.keys(w.files)) {
        const m = new RegExp(`${heldDir}/([0-9a-f]{64})\\.approved$`).exec(f);
        if (m && m[1].startsWith(h8)) hits.add(m[1]);
      }
      if (hits.size !== 1)
        return { value: { exitCode: 2, stdout: `{"error":"no held draft matching ${h8}"}`, stderr: '' } };
      const h = [...hits][0];
      delete w.files[`${heldDir}/${h}.approved`];
      w.dirs[heldDir] = (w.dirs[heldDir] as { name: string }[])
        .filter((e) => e.name !== `${h}.approved`);
      return { value: { exitCode: 0, stdout: `{"ok":true,"hash":"${h}"}`, stderr: '' } };
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
  });
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
  on('ui.notice', () => ({ value: undefined }));
  on('ui.invalidate', () => ({ value: undefined }));
  on('command.register', () => ({ value: {} }));
  on('clock.every', () => ({ value: undefined }));
  on('session.start', (_$: never, e: { cwd: string }) => ({ cwd: e.cwd }));
  on('tool.call', (_$: never, e: { tool: string }) => ({ result: { ran: e.tool } }));
}

function fresh(over: Partial<Wired> = {}): Wired {
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

// The send-shape rule: the gated text verbatim as its own argument,
// envelope fields only beside it.
const sendCall = () => ({
  tool: 'gmail.send', tool_use_id: 't1',
  to: 'v@x', subject: 're: plan', body: RENDERED,
});

const approvals = (w: Wired) =>
  (w.state.get('betterterms-mod/approvals')?.value ?? {}) as Record<string, true>;

const PANE_PROPS = {
  title: 'betterterms', isFocused: true, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 30 }, view: {},
};

const BAND_PROPS = {
  hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 120,
  scroll: { offset: 0, bodyRows: 5 }, view: {},
};

for (const surface of ['terminal', 'desktop'] as const) {
  test(`held draft shows band and badge (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const band = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'AbovePrompt', props: BAND_PROPS as never,
    });
    expect(await band.find({ text: /draft waiting/ })).toBeDefined();
    expect(await band.find({ key: 'review' })).toBeDefined();
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    expect(await pane.find({ key: 'tab-2' })).toBeDefined();
    expect(await pane.find({ text: /Approvals \(1\)/ })).toBeDefined();
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    expect(await pane.find({ text: new RegExp(HASH8) })).toBeDefined();
    expect(await pane.find({ key: `approve-${HASH8}` })).toBeDefined();
    await pane.unmount();
    await band.unmount();
  });

  test(`approve sends exactly once (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const denied = await $.tool.call(sendCall() as never);
    expect((denied as { deny?: string }).deny).toMatch(/held for your approval/);
    expect(Object.keys(approvals(w))).toHaveLength(0);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    await pane.press({ key: `approve-${HASH8}` });
    expect(w.runs.some((r) => r.join(' ').includes(`held approve ${ID} ${HASH8}`))).toBe(true);
    expect(approvals(w)[HASH]).toBe(true);
    expect(w.prompts).toEqual([
      `betterterms: the user approved draft ${HASH8} for ${ID}. ` +
      'Send it now: the approved text verbatim as its own argument, ' +
      'nothing added. The send guard re-runs the gate; do not run it yourself.',
    ]);
    const sent = await $.tool.call(sendCall() as never);
    expect((sent as { result?: { ran: string } }).result?.ran).toBe('gmail.send');
    expect(w.runs.some((r) => r.includes('--approved'))).toBe(true);
    const third = await $.tool.call(sendCall() as never);
    expect((third as { deny?: string }).deny).toMatch(/held for your approval/);
    await pane.unmount();
  });

  test(`click and key both approve (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    // press() is the kit's act for a mouse click and a hotkey press alike.
    await pane.press({ key: `approve-${HASH8}` });
    expect(approvals(w)[HASH]).toBe(true);
    await pane.unmount();
  });

  test(`resend with different text denied (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    await pane.press({ key: `approve-${HASH8}` });
    expect(approvals(w)[HASH]).toBe(true);
    // The resend's render hashes to HASH2 (edited text); the approval
    // for HASH must not cover it.
    w.gateText = () => GATE_HELD.replace(HASH, HASH2);
    const out = await $.tool.call(sendCall() as never);
    expect((out as { deny?: string }).deny).toMatch(/held for your approval/);
    expect(approvals(w)[HASH]).toBe(true);
    await pane.unmount();
  });

  test(`a forged marker with no $.state press stays denied (${surface})`, async ($, on) => {
    // Only $.state counts: a .approved file left on disk is never
    // adopted, never spent, never a send.
    const w = fresh({
      files: fixtureFiles({ [`${DIR}/held/${HASH}.approved`]: 'hash: forged\n' }),
    });
    (w.dirs[`${DIR}/held`] as unknown[]).push({ name: `${HASH}.approved`, kind: 'file', isLink: false });
    wire(on as OpHook, w);
    const out = await $.tool.call(sendCall() as never);
    expect((out as { deny?: string }).deny).toMatch(/held for your approval/);
    expect(`${DIR}/held/${HASH}.approved` in w.files).toBe(true);
    expect(w.runs.some((r) => r.includes('--approved'))).toBe(false);
    expect(Object.keys(approvals(w))).toHaveLength(0);
  });

  test(`a typed bt approve records $.state and sends once (${surface})`, async ($, on) => {
    // `bt approve` typed in the prompt reaches the mod's own
    // prompt.submit hook: the typed hash8 must prefix-match the
    // case's current gate.json hash, then the full hash lands in
    // $.state. The resend spends it once.
    const w = fresh();
    wire(on as OpHook, w);
    await $.prompt.submit({
      text: `bt approve ${ID} ${HASH8}`, wait: false,
      origin: { kind: 'composer' },
    } as never);
    expect(approvals(w)[HASH]).toBe(true);
    const sent = await $.tool.call(sendCall() as never);
    expect((sent as { result?: { ran: string } }).result?.ran).toBe('gmail.send');
    expect(w.runs.some((r) => r.includes('--approved'))).toBe(true);
    const again = await $.tool.call(sendCall() as never);
    expect((again as { deny?: string }).deny).toMatch(/held for your approval/);
  });

  test(`a stale held hash refuses the press (${surface})`, async ($, on) => {
    // gate.json names the draft the last gate verdict held; a card
    // whose hash does not match it belongs to old text (an edit
    // already replaced it), so the press refuses plainly.
    const w = fresh({
      files: fixtureFiles({
        [`${DIR}/gate.json`]: JSON.stringify({
          result: 'needs_approval',
          reasons: ["action 'cancel' requires --approved"],
          rendered: 'a different held text',
          hash: HASH2,
        }),
      }),
    });
    wire(on as OpHook, w);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    await pane.press({ key: `approve-${HASH8}` });
    expect(approvals(w)[HASH]).toBeUndefined();
    expect(w.runs.some((r) => r.join(' ').includes(`held approve`))).toBe(false);
    expect(w.prompts).toHaveLength(0);
    expect(w.toasts.some((t) => /not the current held draft/.test(t))).toBe(true);
    await pane.unmount();
  });

  test(`a re-gate miss disarms the re-armed marker (${surface})`, async ($, on) => {
    // The press stands in $.state but the marker is gone, so the mod
    // re-arms it; the re-gate then answers for a different draft and
    // cannot spend it, so the mod removes it again.
    const w = fresh();
    wire(on as OpHook, w);
    w.state.set('betterterms-mod/approvals', { value: { [HASH]: true }, version: 1 });
    let call = 0;
    const other = GATE_HELD.replace(HASH, HASH2);
    w.gateText = () => (call++ === 0 ? GATE_HELD : other);
    const out = await $.tool.call(sendCall() as never);
    expect((out as { deny?: string }).deny).toMatch(/betterterms/);
    expect(w.runs.some((r) => r.join(' ').includes(`held disarm ${ID} ${HASH8}`))).toBe(true);
    expect(`${DIR}/held/${HASH}.approved` in w.files).toBe(false);
  });

  test(`throwing gate denies send (${surface})`, async ($, on) => {
    const w = fresh({ throwGate: true });
    wire(on as OpHook, w);
    const out = await $.tool.call(sendCall() as never);
    expect((out as { deny?: string }).deny).toMatch(/betterterms/);
  });

  test(`narrow terminal shows band without pane (${surface})`, async ($, on) => {
    const w = fresh({ openPlaced: false });
    wire(on as OpHook, w);
    await $.session.start({ cwd: '/w', surface, isInteractive: true } as never);
    expect(w.opens).toContain('betterterms');
    expect(w.statuses).toContain('bt: 1 case · $1440/yr saved');
    const band = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'AbovePrompt',
      props: { ...BAND_PROPS, bodyColumns: 120 } as never,
      viewport: { columns: 120, rows: 40 },
    });
    expect(await band.find({ text: /draft waiting/ })).toBeDefined();
    await band.unmount();
  });

  test(`gate rows redrawn (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const props = {
      tool: 'Bash', tool_use_id: 'tu1',
      input: { command: `python3 /x/skills/betterterms-guardrails/scripts/bt.py gate ${ID} --draft ${DIR}/draft.yaml` },
      isRunning: false, isErrored: false, isInterrupted: false,
      output: { stdout: '{"result":"pass","reasons":[]}', stderr: '', interrupted: false },
    };
    const row = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'ToolUse', props: props as never,
    });
    expect(await row.find({ text: /Gate pass/ })).toBeDefined();
    await row.redraw({
      ...props,
      output: { stdout: '{"result":"block","reasons":["outside your limits"]}', stderr: '', interrupted: false },
    } as never);
    expect(await row.find({ text: /Gate block: outside your limits/ })).toBeDefined();
    await row.redraw({
      ...props,
      output: { stdout: GATE_HELD, stderr: '', interrupted: false },
    } as never);
    expect(await row.find({ text: /Held for you/ })).toBeDefined();
    await row.unmount();
  });

  test(`status line text (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    await $.session.start({ cwd: '/w', surface, isInteractive: true } as never);
    expect(w.statuses).toContain('bt: 1 case · $1440/yr saved');
  });
}
