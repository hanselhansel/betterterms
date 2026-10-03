// Engine-side tests for `claude plugin test ./mod`. Named .tsx on
// purpose: `node --test` discovers .test.ts and .test.js but leaves .tsx
// alone, and plain node cannot resolve `claude-code/testing`. The unit
// suite lives in register.test.js.
//
// The kit loads this plugin itself. `on` answers the op events the mod
// calls: env, fs, process.run (the gate), tool.call (the real call).

import { test, expect } from 'claude-code/testing';

const ID = 'bills-20261003-a1b2';
const DIR = `/bt/cases/${ID}`;
const BRIEF = 'pack: bills\nmode: act\nautonomy: 4\n';
const DRAFT_TEXT = 'I can pay $1,000 a year for this plan.';
const DRAFT = `action: send\noffer: 1000\ntext: '${DRAFT_TEXT}'\nclaims: []\n`;
const THREAD = `# thread ${ID}\n## in 2026-10-03T15:04:05+00:00 approved_by_user: no\nhi\n`;

const FILES: Record<string, string> = {
  [`${DIR}/brief.yaml`]: BRIEF,
  [`${DIR}/thread.md`]: THREAD,
  [`${DIR}/draft.yaml`]: DRAFT,
};

const DIRS: Record<string, unknown[]> = {
  '/bt/cases': [{ name: ID, kind: 'dir', isLink: false }],
  [`${DIR}/sources`]: [],
};

type OpHook = (event: string, hook: (...a: never[]) => unknown) => unknown;

function wire(on: OpHook, gateStdout: string) {
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
  on('process.run', () => ({
    value: { exitCode: 0, stdout: gateStdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
  }));
  on('tool.call', (_$: never, e: { tool: string }) => ({ result: { ran: e.tool } }));
}

test('an unrelated call passes through to the tool', async ($, on) => {
  wire(on as OpHook, '{"result":"pass","reasons":[]}');
  const out = await $.tool.call({ tool: 'Bash', command: 'ls -la' } as never);
  expect((out as { result: { ran: string } }).result.ran).toBe('Bash');
});

test('a send carrying the draft is denied on a gate block', async ($, on) => {
  wire(on as OpHook, '{"result":"block","reasons":["floor disclosed in draft text"]}');
  const out = await $.tool.call({
    tool: 'Bash',
    command: `mail vendor@x <<EOF\n${DRAFT_TEXT}\nEOF`,
  } as never);
  expect((out as { deny?: string }).deny).toMatch(/betterterms/);
});

test('a send at autonomy 4 goes through on a gate pass', async ($, on) => {
  wire(on as OpHook, '{"result":"pass","reasons":[]}');
  const out = await $.tool.call({
    tool: 'Bash',
    command: `send ${DRAFT_TEXT}`,
  } as never);
  expect((out as { result: { ran: string } }).result.ran).toBe('Bash');
});
