// Engine-side approval-flow tests for `claude plugin test ./mod`.
// Named .tsx on purpose, like register.test.tsx: `node --test`
// discovers .test.ts and .test.js but leaves .tsx alone, and plain
// node cannot resolve `claude-code/testing`. The fake world lives in
// approvals.fixture.tsx; the ui-surface tests live in
// surfaces.test.tsx.
//
// The mod is a cockpit only (decision 0020): no tool.call or
// prompt.submit interception. The Approve press writes the hash-bound
// marker through `held approve` and submits the prompt that sends the
// agent through `gate --approved` once; the marker is the consent the
// gate spends.

import { test, expect } from 'claude-code/testing';
import {
  ID, DIR, HASH, HASH8, HASH2, GATE_HELD, fixtureFiles, fresh, wire,
  processRun, PANE_PROPS, type OpHook,
} from './approvals.fixture.tsx';

// The submitted prompt carries one runnable command inside
// backticks; parse it out and return the argv.
function promptArgv(w: { prompts: string[] }): string[] {
  const m = /`([^`]+)`/.exec(w.prompts[0] ?? '');
  expect(m).not.toBeNull();
  return m![1].split(' ');
}

for (const surface of ['terminal', 'desktop'] as const) {
  test(`approve press arms the marker and submits the gate prompt (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    await pane.press({ key: `approve-${HASH8}` });
    expect(w.runs.some((r) => r.join(' ').includes(`held approve ${ID} ${HASH8}`))).toBe(true);
    expect(`${DIR}/held/${HASH}.approved` in w.files).toBe(true);
    expect(w.prompts).toHaveLength(1);
    expect(w.prompts[0]).toContain(`approved draft ${HASH8} for ${ID}`);
    // The command is the mod's own gate argv -- the resolved absolute
    // bt.py path, the case's draft path, --approved -- told once.
    const argv = promptArgv(w);
    expect(argv[0]).toBe('python3');
    expect(argv[1].endsWith('skills/betterterms-guardrails/scripts/bt.py')).toBe(true);
    expect(argv.slice(2)).toEqual([
      'gate', ID, '--draft', `${DIR}/draft.yaml`, '--approved',
    ]);
    expect(w.prompts[0]).toContain('exactly once');
    expect(w.prompts[0]).toContain('verbatim as its own argument');
    // Consent lives only in the marker: no $.state entry is written.
    expect(w.state.get('betterterms-mod/approvals')).toBeUndefined();
    await pane.unmount();
  });

  test(`the prompt names --inbound when the case carries one (${surface})`, async ($, on) => {
    const w = fresh({
      files: fixtureFiles({ [`${DIR}/inbound.yaml`]: 'offer: 1000\n' }),
    });
    wire(on as OpHook, w);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    await pane.press({ key: `approve-${HASH8}` });
    const argv = promptArgv(w);
    const i = argv.indexOf('--inbound');
    expect(i).toBeGreaterThan(-1);
    expect(argv[i + 1]).toBe(`${DIR}/inbound.yaml`);
    expect(argv[argv.length - 1]).toBe('--approved');
    await pane.unmount();
  });

  test(`the marker spends exactly once through the prompt's command (${surface})`, async ($, on) => {
    const w = fresh();
    wire(on as OpHook, w);
    const pane = await $.ui.mount({
      plugin: 'betterterms-mod', surface, component: 'Pane',
      props: PANE_PROPS as never, requestId: 'betterterms',
    });
    await pane.press({ key: 'tab-2' });
    await pane.redraw();
    await pane.press({ key: `approve-${HASH8}` });
    await pane.unmount();
    // The agent does what the prompt says: the emitted command run
    // verbatim passes and spends marker plus record; the same call
    // again is held all over (needs_approval, exit 3).
    const argv = promptArgv(w);
    const once = processRun(w, argv).value;
    expect(once.stdout).toContain('"pass"');
    expect(`${DIR}/held/${HASH}.approved` in w.files).toBe(false);
    expect(`${DIR}/held/${HASH}.yaml` in w.files).toBe(false);
    const twice = processRun(w, argv).value;
    expect(twice.exitCode).toBe(3);
    expect(twice.stdout).toContain('needs_approval');
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
    expect(`${DIR}/held/${HASH}.approved` in w.files).toBe(true);
    expect(w.prompts).toHaveLength(1);
    await pane.unmount();
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
    expect(`${DIR}/held/${HASH}.approved` in w.files).toBe(false);
    expect(w.runs.some((r) => r.join(' ').includes(`held approve`))).toBe(false);
    expect(w.prompts).toHaveLength(0);
    expect(w.toasts.some((t) => /not the current held draft/.test(t))).toBe(true);
    await pane.unmount();
  });

  test(`tool calls and prompts pass straight through (${surface})`, async ($, on) => {
    // No tool.call or prompt.submit hook is registered: a call that
    // carries the gated text, a typed `bt approve`, anything at all
    // reaches the underlying op untouched.
    const w = fresh();
    wire(on as OpHook, w);
    const sent = await $.tool.call({
      tool: 'gmail.send', tool_use_id: 't1',
      to: 'v@x', subject: 'Re: plan',
      body: 'I can pay $1,000 a year for this plan.',
    } as never);
    expect((sent as { result?: { ran: string } }).result?.ran).toBe('gmail.send');
    const prompt = await $.prompt.submit({
      text: `bt approve ${ID} ${HASH8}`, wait: false,
      origin: { kind: 'composer' },
    } as never);
    expect((prompt as { text: string }).text).toBe(`bt approve ${ID} ${HASH8}`);
    expect(w.runs.filter((r) => r.join(' ').includes('gate'))).toHaveLength(0);
    expect(w.state.get('betterterms-mod/approvals')).toBeUndefined();
    expect(GATE_HELD).toBe(w.files[`${DIR}/gate.json`]);
  });
}
