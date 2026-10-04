// Engine-side approval-flow tests for `claude plugin test ./mod`.
// Named .tsx on purpose, like register.test.tsx: `node --test`
// discovers .test.ts and .test.js but leaves .tsx alone, and plain
// node cannot resolve `claude-code/testing`. The fake world lives in
// approvals.fixture.tsx; the ui-surface tests live in
// surfaces.test.tsx.

import { test, expect } from 'claude-code/testing';
import {
  ID, DIR, HASH, HASH8, HASH2, GATE_HELD, fixtureFiles, fresh, wire,
  sendCall, approvals, PANE_PROPS, type OpHook,
} from './approvals.fixture.tsx';

for (const surface of ['terminal', 'desktop'] as const) {
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
}
