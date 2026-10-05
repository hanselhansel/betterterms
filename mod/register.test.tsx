// Engine-side tests for `claude plugin test ./mod`. Named .tsx on
// purpose: `node --test` discovers .test.ts and .test.js but leaves .tsx
// alone, and plain node cannot resolve `claude-code/testing`. The unit
// suite lives in register.test.js.
//
// The kit loads this plugin itself. `on` answers the op events the mod
// calls: env, fs, process.run (the gate), tool.call (the real call).
// The mod registers no tool.call or prompt.submit hook (decision
// 0020), so every event reaches the underlying op untouched.

import { test, expect } from 'claude-code/testing';

const ID = 'bills-20261003-a1b2';
const DIR = `/bt/cases/${ID}`;
const BRIEF = 'pack: bills\nmode: act\nautonomy: 4\n';
const RENDERED = 'I can pay $1,000 a year for this plan.';
const DRAFT = `action: send\noffer: 1000\ntemplate: 'I can pay {offer} a year for this plan.'\nclaims: []\n`;
// gate.json: the last verdict the exchange skill saved for the draft.
const GATE = JSON.stringify({ result: 'pass', reasons: [], rendered: RENDERED });
const THREAD = `# thread ${ID}\n## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;

const FILES: Record<string, string> = {
  [`${DIR}/brief.yaml`]: BRIEF,
  [`${DIR}/thread.md`]: THREAD,
  [`${DIR}/draft.yaml`]: DRAFT,
  [`${DIR}/gate.json`]: GATE,
};

const DIRS: Record<string, unknown[]> = {
  '/bt/cases': [{ name: ID, kind: 'dir', isLink: false }],
  [`${DIR}/sources`]: [],
};

type OpHook = (event: string, hook: (...a: never[]) => unknown) => unknown;

function wire(on: OpHook) {
  on('env.get', (_$: never, e: { name: string }) => ({
    value: e.name === 'BETTERTERMS_HOME' ? '/bt' : '/u',
  }));
  on('fs.read', (_$: never, e: { path: string }) =>
    e.path in FILES ? { value: FILES[e.path] } : { deny: 'ENOENT' });
  on('fs.list', (_$: never, e: { path: string }) => ({ value: DIRS[e.path] ?? [] }));
  on('fs.exists', (_$: never, e: { path: string }) => ({
    value: e.path in FILES || e.path in DIRS || e.path.endsWith('scripts/bt.py'),
  }));
  on('fs.stat', (_$: never, e: { path: string }) =>
    e.path in FILES || e.path in DIRS
      ? { value: { kind: e.path in DIRS ? 'dir' : 'file', size: 1, mtimeMs: 2, isLink: false, realPath: e.path } }
      : { deny: 'ENOENT' });
  on('tool.call', (_$: never, e: { tool: string }) => ({ result: { ran: e.tool } }));
  on('prompt.submit', (_$: never, e: { text: string }) => ({ text: e.text }));
}

test('an unrelated call passes through to the tool', async ($, on) => {
  wire(on as OpHook);
  const out = await $.tool.call({ tool: 'Bash', command: 'ls -la' } as never);
  expect((out as { result: { ran: string } }).result.ran).toBe('Bash');
});

test('a call carrying the gated text is not intercepted', async ($, on) => {
  // The send check is gone (decision 0020): even a send-shaped call
  // with the gated text verbatim reaches the tool untouched. The
  // gate's --approved marker is the only enforcement, inside bt.py.
  wire(on as OpHook);
  const out = await $.tool.call({
    tool: 'gmail.send',
    to: 'v@x', subject: 'Re: plan', body: RENDERED,
  } as never);
  expect((out as { result: { ran: string } }).result.ran).toBe('gmail.send');
});

test('a typed bt approve passes through to the prompt', async ($, on) => {
  // No prompt.submit hook either: the settings hook (not the mod)
  // handles `bt approve` when the core plugin's hooks are loaded.
  wire(on as OpHook);
  const out = await $.prompt.submit({
    text: `bt approve ${ID} abcdef12`, origin: { kind: 'composer' },
  } as never);
  expect((out as { text: string }).text).toBe(`bt approve ${ID} abcdef12`);
});
