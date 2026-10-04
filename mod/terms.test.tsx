// Engine-side terms-editor and savings tests for `claude plugin test
// ./mod` (spec 6.4, 6.5). Named .tsx on purpose, like register.test.tsx:
// `node --test` discovers .test.ts and .test.js but leaves .tsx alone,
// and plain node cannot resolve `claude-code/testing`.
//
// The kit loads this plugin itself, Clients and all. `on` answers the
// op events the mod calls: env, fs, state, process.run (bt.py) and the
// ui surface calls. The walk-away (900) may only ever travel through a
// run's init.stdin; these tests assert it never lands in argv.

import { test, expect } from 'claude-code/testing';

const ID = 'bills-20261003-a1b2';
const DIR = `/bt/cases/${ID}`;
const BRIEF = 'pack: bills\nmode: act\ndirection: pay\nautonomy: 4\n';
const DRAFT = `action: send\noffer: 1000\ntemplate: 'I can pay {offer} a year for this plan.'\nclaims: []\n`;
const THREAD = `# thread ${ID}\n## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;
// plan.yaml: target 800, best alternative 850/month, offer 1000 after
// a start of 1100. .floor: 900.00.
const PLAN = [
  'currency: USD',
  'target: 800',
  'best_alternative:',
  '  amount: 850',
  '  period: month',
  '  note: TMobile quote',
  'facts:',
  '- 1100',
  '- 1000',
  '',
].join('\n');
const LEDGER_TOTAL =
  '{"cases":3,"by_currency":{"USD":1440},"by_pack":{"bills":{"USD":1440}},"warnings":0}';
const LEDGER = [
  '{"case_id":"a-20260101-aaaa","saved_per_year":240,"recorded_at":"2026-09-07T00:00:00Z"}',
  '{"case_id":"b-20260201-bbbb","saved_per_year":-100,"recorded_at":"2026-09-14T00:00:00Z"}',
  '{"case_id":"c-20260301-cccc","saved_per_year":1300,"recorded_at":"2026-09-14T12:00:00Z"}',
].join('\n');

type Files = Record<string, string>;
type Dirs = Record<string, unknown[]>;
type OpHook = (event: string, hook: (...a: never[]) => unknown) => unknown;
interface Run {
  argv: string[];
  stdin?: string;
}
interface Wired {
  files: Files;
  dirs: Dirs;
  state: Map<string, { value: unknown; version: number }>;
  runs: Run[];
  toasts: string[];
}

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
  on('fs.write', () => ({ value: undefined }));
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
  on('process.run', (_$: never, e: { argv: string[]; init?: { stdin?: string } }) => {
    const argv = e.argv.map(String);
    w.runs.push({ argv, stdin: e.init?.stdin });
    if (argv.includes('ledger'))
      return { value: { exitCode: 0, stdout: LEDGER_TOTAL, stderr: '' } };
    return { value: { exitCode: 0, stdout: '{"ok":true}', stderr: '' } };
  });
  on('ui.open', () => ({ value: { isPlaced: true } }));
  on('ui.status', () => ({ value: undefined }));
  on('ui.toast', (_$: never, e: { text: string }) => { w.toasts.push(e.text); return { value: undefined }; });
  on('ui.notice', () => ({ value: undefined }));
  on('ui.invalidate', () => ({ value: undefined }));
  on('command.register', () => ({ value: {} }));
  on('clock.every', () => ({ value: undefined }));
  on('session.start', (_$: never, e: { cwd: string }) => ({ cwd: e.cwd }));
  on('tool.call', (_$: never, e: { tool: string }) => ({ result: { ran: e.tool } }));
}

function fresh(): Wired {
  return {
    files: {
      [`${DIR}/brief.yaml`]: BRIEF,
      [`${DIR}/thread.md`]: THREAD,
      [`${DIR}/draft.yaml`]: DRAFT,
      [`${DIR}/plan.yaml`]: PLAN,
      [`${DIR}/.floor`]: '900.00\n',
      '/bt/ledger.jsonl': LEDGER,
    },
    dirs: {
      '/bt/cases': [{ name: ID, kind: 'dir', isLink: false }],
      [`${DIR}/sources`]: [],
    },
    state: new Map(),
    runs: [],
    toasts: [],
  };
}

const PANE_PROPS = {
  title: 'betterterms', isFocused: true, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 30 }, view: {},
};

// Mounts the pane, selects the one case and opens its terms editor.
async function openTerms($: never, surface: 'terminal' | 'desktop') {
  const pane = await ($ as { ui: { mount: (t: unknown) => Promise<never> } }).ui.mount({
    plugin: 'betterterms-mod', surface, component: 'Pane',
    props: PANE_PROPS as never, requestId: 'betterterms',
  });
  const p = pane as {
    press: (q: { key: string }) => Promise<void>;
    redraw: () => Promise<void>;
    find: (q: unknown) => Promise<never>;
  };
  await p.press({ key: `case-${ID}` });
  await p.redraw();
  await p.press({ key: `terms-${ID}` });
  await p.redraw();
  return pane as never;
}

for (const surface of ['terminal', 'desktop'] as const) {
  test(`terms editor opens on t and shows the walk-away (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await openTerms($, surface) as {
      find: (q: unknown) => Promise<{ text?: string; props?: Record<string, unknown> } | undefined>;
      unmount: () => Promise<void>;
    };
    expect(await pane.find({ key: 'scale' })).toBeDefined();
    const walk = await pane.find({ key: 'term-walkaway' });
    expect(walk?.text).toBe('900');
    expect((await pane.find({ key: 'term-target' }))?.text).toBe('800');
    expect((await pane.find({ key: 'term-alternative' }))?.text).toBe('850');
    await pane.unmount();
  });

  test(`all three fields follow a drag (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await openTerms($, surface) as {
      pointer: (e: { type: string; x: number; y: number; button?: string; in: string }) => Promise<void>;
      redraw: () => Promise<void>;
      find: (q: unknown) => Promise<{ text?: string } | undefined>;
      unmount: () => Promise<void>;
    };
    // Values 800/850/900 + offer 1000 fit to [750, 1050]: a 300-dollar
    // span over the 40-column bar. Handle columns: target 7, alt 13,
    // walk-away 20. The mount draws again only on redraw: a hook's
    // invalidate marks the drawing dirty until then.
    await pane.pointer({ type: 'down', x: 7, y: 0, button: 'left', in: 'scale' });
    await pane.pointer({ type: 'move', x: 10, y: 0, button: 'left', in: 'scale' });
    await pane.pointer({ type: 'up', x: 10, y: 0, button: 'left', in: 'scale' });
    await pane.redraw();
    expect((await pane.find({ key: 'term-target' }))?.text).toBe('827');
    // After the release the range refits to [783.75, 1043.25].
    await pane.pointer({ type: 'down', x: 10, y: 0, button: 'left', in: 'scale' });
    await pane.pointer({ type: 'move', x: 13, y: 0, button: 'left', in: 'scale' });
    await pane.pointer({ type: 'up', x: 13, y: 0, button: 'left', in: 'scale' });
    await pane.redraw();
    expect((await pane.find({ key: 'term-alternative' }))?.text).toBe('870');
    await pane.pointer({ type: 'down', x: 17, y: 0, button: 'left', in: 'scale' });
    await pane.pointer({ type: 'move', x: 20, y: 0, button: 'left', in: 'scale' });
    await pane.pointer({ type: 'up', x: 20, y: 0, button: 'left', in: 'scale' });
    await pane.redraw();
    expect((await pane.find({ key: 'term-walkaway' }))?.text).toBe('917');
    await pane.unmount();
  });

  test(`minus and plus nudge by 1 (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await openTerms($, surface) as {
      key: (e: { key: string; in: string }) => Promise<void>;
      press: (q: { key: string }) => Promise<void>;
      redraw: () => Promise<void>;
      find: (q: unknown) => Promise<{ text?: string } | undefined>;
      unmount: () => Promise<void>;
    };
    await pane.key({ key: '-', in: 'scale' });
    await pane.redraw();
    expect((await pane.find({ key: 'term-target' }))?.text).toBe('799');
    await pane.key({ key: '+', in: 'scale' });
    await pane.redraw();
    expect((await pane.find({ key: 'term-target' }))?.text).toBe('800');
    await pane.key({ key: 'tab', in: 'scale' });
    await pane.key({ key: '-', in: 'scale' });
    await pane.redraw();
    expect((await pane.find({ key: 'term-alternative' }))?.text).toBe('849');
    await pane.press({ key: 'nudge-plus' });
    await pane.redraw();
    expect((await pane.find({ key: 'term-alternative' }))?.text).toBe('850');
    await pane.unmount();
  });

  test(`z toggles full range (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await openTerms($, surface) as {
      key: (e: { key: string; in: string }) => Promise<void>;
      press: (q: { key: string }) => Promise<void>;
      redraw: () => Promise<void>;
      find: (q: unknown) => Promise<{ props?: { props?: { lo?: number; hi?: number } } } | undefined>;
      unmount: () => Promise<void>;
    };
    const range = async () => (await pane.find({ key: 'scale' }))?.props?.props;
    expect(await range()).toMatchObject({ lo: 750, hi: 1050 });
    await pane.key({ key: 'z', in: 'scale' });
    await pane.redraw();
    expect(await range()).toMatchObject({ lo: 400, hi: 1500 });
    await pane.press({ key: 'range-toggle' });
    await pane.redraw();
    expect(await range()).toMatchObject({ lo: 750, hi: 1050 });
    await pane.unmount();
  });

  test(`save writes walk-away through stdin, never argv (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await openTerms($, surface) as {
      press: (q: { key: string }) => Promise<void>;
      unmount: () => Promise<void>;
    };
    await pane.press({ key: 'save-terms' });
    const floor = w.runs.find((r) => r.argv.includes('set-floor'));
    expect(floor).toBeDefined();
    expect(floor?.stdin).toBe('900\n');
    for (const r of w.runs) {
      expect(r.argv.some((a) => a.includes('900'))).toBe(false);
    }
    const terms = w.runs.find((r) => r.argv.includes('set-terms'));
    expect(terms?.argv.join(' ')).toContain('--target 800');
    expect(terms?.argv.join(' ')).toContain('--alternative 850');
    expect(w.toasts.some((t) => /terms saved/.test(t))).toBe(true);
    await pane.unmount();
  });

  test(`savings draws Svg on desktop and Raster on terminal (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-3' });
    await pane.redraw();
    expect(await pane.find({ text: /saved.*1440|1440.*yr/ })).toBeDefined();
    if (surface === 'desktop') {
      expect(await pane.find({ type: 'Svg' })).toBeDefined();
      expect(await pane.find({ type: 'Raster' })).toBeUndefined();
    } else {
      expect(await pane.find({ type: 'Raster' })).toBeDefined();
      expect(await pane.find({ type: 'Svg' })).toBeUndefined();
    }
    expect(await pane.find({ text: /3 closed/ })).toBeDefined();
    await pane.unmount();
  });
}
