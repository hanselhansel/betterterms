// The terms editor's price-scale Client (spec 6.4): pointer drags the
// three handles, Tab moves the focus, - and + nudge by $1, z toggles
// the full range. All layout math lives in ../ui/scale.js; this file
// only turns pointer and key events into posts for the hooks module
// and cells into a tree. Posts carry plain numbers only.

import * as S from "../ui/scale.js";

const HANDLES = [
  { key: "target", mark: "T", color: "green", lane: "above", label: "target" },
  { key: "walkaway", mark: "W", color: "red", lane: "above", label: "walk-away" },
  { key: "alternative", mark: "A", color: "blue", lane: "below", label: "alt" },
];
const TAB_ORDER = ["target", "alternative", "walkaway"];

const labelOf = (key, v) =>
  `${HANDLES.find((hd) => hd.key === key).label} ${v == null ? "?" : String(Math.round(v))}`;

// One cell row to a Text line of color runs (scale.js cellsText).
function row(el, cells, key) {
  return h(
    el.Text,
    { key },
    ...S.cellsText(cells).map((sg, i) =>
      h(el.Text, { key: `s${i}`, color: sg.color, dimColor: sg.color === undefined }, sg.text)),
  );
}

export default function ScaleDrag(props, surface) {
  const el = surface.elements;
  const cols = Math.max(12, Math.min(160, surface.columns || 40));
  const st = surface.state;
  const drag = st?.drag ?? null;
  const vals = drag ? st.values : (props.values ?? {});
  const lo = Number(props.lo) || 0;
  const hi = Number(props.hi) || 100;
  const offer = Number(props.offer);
  const xs = S.handleXs(vals, lo, hi, cols, HANDLES.map((hd) => hd.key));

  surface.onPointer((e) => {
    const cur = surface.state ?? { drag: null, values: { ...(props.values ?? {}) } };
    const x = Math.round(e.fine?.x ?? e.x);
    if (e.type === "down" && (e.button === undefined || e.button === "left")) {
      const hit = S.nearestHandle(x, S.handleXs(vals, lo, hi, cols, HANDLES.map((hd) => hd.key)));
      if (hit !== null) {
        surface.setState({ ...cur, drag: hit, values: { ...vals } });
        surface.post({ type: "focus", handle: hit });
      }
    } else if (e.type === "move" && cur.drag) {
      const v = S.xToValue(x, lo, hi, cols);
      if (v !== cur.values[cur.drag]) {
        surface.setState({ ...cur, values: { ...cur.values, [cur.drag]: v } });
        surface.post({ type: "value", handle: cur.drag, value: v });
      }
    } else if (e.type === "up" && cur.drag) {
      surface.setState({ ...cur, drag: null });
      surface.post({ type: "release", handle: cur.drag });
    }
  });

  surface.onKey((e) => {
    if (e.key === "tab") {
      const i = TAB_ORDER.indexOf(props.focused ?? "target");
      const next = TAB_ORDER[(i + (e.shift ? TAB_ORDER.length - 1 : 1)) % TAB_ORDER.length];
      surface.post({ type: "focus", handle: next });
    } else if (e.key === "-") surface.post({ type: "nudge", delta: -1 });
    else if (e.key === "+" || e.key === "=") surface.post({ type: "nudge", delta: 1 });
    else if (e.key === "z") surface.post({ type: "full" });
    else if (e.key === "s") surface.post({ type: "save" });
  });

  // Above lanes: tier-0 labels on row 0; row 1 stacks the spilled
  // labels and leads the tier-0 handles down to the bar.
  const above = HANDLES.filter((hd) => hd.lane === "above")
    .map((hd) => ({ key: hd.key, col: xs[hd.key], color: hd.color, label: labelOf(hd.key, vals[hd.key]) }));
  const aboveLanes = S.lanes(above);
  const tier0 = aboveLanes.filter((hd) => hd.tier === 0);
  const spilled = aboveLanes.filter((hd) => hd.tier > 0);
  const below = HANDLES.filter((hd) => hd.lane === "below")
    .map((hd) => ({ key: hd.key, col: xs[hd.key], color: hd.color, label: labelOf(hd.key, vals[hd.key]) }));
  const bar = S.barCells({
    values: vals, offer: Number.isFinite(offer) ? offer : null,
    lo, hi, cols, handles: HANDLES,
  }).map((c) => ({
    ch: c.ch,
    color: c.handle === "offer" ? "gray" : HANDLES.find((hd) => hd.key === c.handle)?.color,
  }));

  return h(
    el.Box,
    { flexDirection: "column" },
    row(el, S.labelCells(tier0, [], cols), "lane0"),
    row(el, S.labelCells(spilled, tier0.map((hd) => hd.col), cols), "lane1"),
    row(el, bar, "bar"),
    row(el, S.labelCells(below, below.map((hd) => hd.col), cols), "below"),
  );
}
