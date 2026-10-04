// The betterterms pane (spec 6.1-6.3): three tabs —
//   1 Cases      one card per case, selected shows the offer bar,
//                the six-step strip and a note
//   2 Approvals  one card per held draft, oldest first, with the
//                rendered text, the gate's reasons, and the three
//                actions: Approve and send (a), Edit (e), Reject (r)
//   3 Savings    the ledger totals (charts land in a later task)
//
// Trees only: the hook resolves the element set and hands `view`
// ({tab, selected, editing}) plus `act` (the press handlers from
// lib/approvals.js). Arrow keys are never bound: rows and cards are
// Buttons and Inputs, which both pointer and hotkey press.

import * as C from "../lib/cases.js";
import { hash8 } from "../lib/approvals.js";

const MONEY = /(?:[$€£]\s?|(?:CHF|USD|EUR|GBP)\s)\d[\d,]*(?:\.\d{1,2})?|\b\d[\d,]*(?:\.\d{1,2})?\s?(?:\/(?:mo|month|yr|year)|\bper\s(?:month|year))|\$\d[\d,]*/g;

function tabs(el, view, heldN) {
  const { Box, Button } = el;
  const tab = (n, label) => h(Button, {
    key: `tab-${n}`,
    label,
    hotkey: String(n),
    variant: view.tab === n ? "primary" : "secondary",
    onPress: () => view.act.openTab(n),
  });
  return h(
    Box,
    { key: "tabs" },
    tab(1, "1 Cases"),
    h(el.Text, null, "  "),
    tab(2, `2 Approvals (${heldN})`),
    h(el.Text, null, "  "),
    tab(3, "3 Savings"),
  );
}

// The offer bar: start, their offer and target on one scale. Terminal
// block style for both surfaces at v1 (the animated SVG is the terms
// editor's, a later task).
function offerBar(marks) {
  const vals = [marks.start, marks.offer, marks.target].filter((v) => v !== null);
  if (vals.length === 0) return null;
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = Math.max(hi - lo, 1e-9);
  const w = 28;
  const cells = new Array(w).fill("─");
  const put = (v, ch) => {
    if (v === null) return;
    cells[Math.round(((v - lo) / span) * (w - 1))] = ch;
  };
  put(marks.start, "S");
  put(marks.offer, "O");
  put(marks.target, "T");
  const money = (v) => v === null ? "?" : `${marks.currency === "USD" ? "$" : `${marks.currency} `}${v}`;
  return {
    bar: `[${cells.join("")}]`,
    legend: `start ${money(marks.start)} · offer ${money(marks.offer)} · target ${money(marks.target)}`,
  };
}

function casesTab(el, snap, view) {
  const { Box, Text, Button } = el;
  const rows = [];
  for (const c of snap.cases) {
    const stage = c.stage === "exchange" ? "in exchange" : c.stage;
    rows.push(h(Button, {
      key: `case-${c.id}`,
      label: `${c.id}  [${stage}]  ${c.next}`,
      dimColor: c.stage === "closed",
      plain: true,
      onPress: () => view.act.select(c.id),
    }));
    if (view.selected === c.id) {
      rows.push(h(Text, { key: `strip-${c.id}`, dimColor: true }, C.progressStrip(c)));
      const bar = c.offer ? offerBar(c.offer) : null;
      if (bar) {
        rows.push(h(Text, { key: `bar-${c.id}` }, bar.bar));
        rows.push(h(Text, { key: `scale-${c.id}`, dimColor: true }, bar.legend));
      }
      if (c.lastSnippet) {
        rows.push(h(Text, { key: `note-${c.id}`, dimColor: true }, `last: ${c.lastSnippet}`));
      }
    }
  }
  if (snap.cases.length === 0) {
    rows.push(h(Text, { dimColor: true }, "no cases yet"));
  }
  return h(Box, { key: "cases", flexDirection: "column" }, ...rows);
}

// The rendered text with money and rate spans drawn bright, so the
// numbers that changed stand out (spec 6.3).
function moneyText(el, text, key) {
  const parts = [];
  let i = 0;
  String(text).replace(MONEY, (m, at) => {
    if (at > i) parts.push({ t: text.slice(i, at), hot: false });
    parts.push({ t: m, hot: true });
    i = at + m.length;
    return m;
  });
  if (i < text.length) parts.push({ t: text.slice(i), hot: false });
  if (parts.length === 0) parts.push({ t: String(text), hot: false });
  return h(
    el.Text,
    { key },
    ...parts.map((p, j) => h(el.Text, { key: `m${j}`, color: p.hot ? "yellow" : undefined }, p.t)),
  );
}

// hotkeys bind only on a lone card: with several held drafts one `a`
// could fire every card at once.
function heldCard(el, c, held, view, single) {
  const { Box, Text, Button, Input } = el;
  const h8 = hash8(held.hash);
  const hotkey = single ? { approve: "a", edit: "e", reject: "r" } : {};
  const rows = [
    h(Text, { key: `held-h-${h8}`, dimColor: true },
      `${c.id} · held ${held.heldAt || "?"} · ${h8}${held.approved ? " · approved" : ""}`),
    moneyText(el, held.rendered, `held-t-${h8}`),
    ...held.reasons.map((r, i) =>
      h(Text, { key: `held-r-${h8}-${i}`, dimColor: true }, `• ${r}`)),
  ];
  if (view.editing === held.hash) {
    rows.push(h(Input, {
      key: `edit-${h8}`,
      label: "edit",
      value: held.rendered,
      submitLabel: "save",
      onSubmit: (text) => view.act.saveEdit(c, held, text),
    }));
  } else {
    rows.push(h(
      Box,
      { key: `held-b-${h8}` },
      h(Button, {
        key: `approve-${h8}`, label: "Approve and send", hotkey: hotkey.approve,
        variant: "primary", onPress: () => view.act.approve(c, held),
      }),
      h(el.Text, null, " "),
      h(Button, {
        key: `edit-open-${h8}`, label: "Edit", hotkey: hotkey.edit,
        onPress: () => view.act.edit(held),
      }),
      h(el.Text, null, " "),
      h(Button, {
        key: `reject-${h8}`, label: "Reject", hotkey: hotkey.reject,
        onPress: () => view.act.reject(c, held),
      }),
    ));
  }
  return h(Box, { key: `held-${h8}`, flexDirection: "column" }, ...rows);
}

function approvalsTab(el, snap, view) {
  const { Box, Text } = el;
  const pairs = snap.cases.flatMap((c) => (c.held ?? []).map((held) => [c, held]));
  const cards = pairs.map(([c, held]) => heldCard(el, c, held, view, pairs.length === 1));
  if (cards.length === 0) {
    cards.push(h(Text, { key: "held-none", dimColor: true }, "nothing held for approval"));
  }
  return h(Box, { key: "approvals", flexDirection: "column" }, ...cards);
}

function savingsTab(el, snap) {
  const { Box, Text } = el;
  const closed = snap.cases.filter((c) => c.stage === "closed").length;
  return h(
    Box,
    { key: "savings", flexDirection: "column" },
    h(Text, null, `saved $${Math.round(snap.savedPerYear)}/yr`),
    h(Text, { dimColor: true }, `${closed} case${closed === 1 ? "" : "s"} closed`),
  );
}

export function paneTree(el, snap, view, act) {
  const v = { ...view, act };
  const heldN = C.heldTotal(snap.cases);
  const body = v.tab === 2
    ? approvalsTab(el, snap, v)
    : v.tab === 3
      ? savingsTab(el, snap)
      : casesTab(el, snap, v);
  return h(
    el.Box,
    { flexDirection: "column" },
    tabs(el, v, heldN),
    h(el.Text, null, " "),
    body,
  );
}
