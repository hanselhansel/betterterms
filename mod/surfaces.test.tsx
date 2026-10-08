// Engine-side ui-surface tests for `claude plugin test ./mod`: the
// AbovePrompt band, the Approvals pane badge, ToolUse gate rows and
// the status line. Named .tsx on purpose, like register.test.tsx;
// the fake world lives in approvals.fixture.tsx and the approval-flow
// tests live in approvals.test.tsx.

import { test, expect } from 'claude-code/testing';
import {
  ID, DIR, HASH8, GATE_HELD, fresh, wire,
  PANE_PROPS, BAND_PROPS, type OpHook,
} from './approvals.fixture.tsx';

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
