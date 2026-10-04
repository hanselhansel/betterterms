// Price-scale layout (spec 6.4): the pure math shared by the terms
// editor's Client, its text fallback and the savings chart cells.
// No $, no host, no I/O: everything here is a function of numbers in.

export const LABEL_W = 12;

// {lo, hi} the bar maps to [0, cols). Normal mode pads the spread by
// 25 percent with at least $4 each side; `full` range is min-50%,
// max+50% rounded to 10 (the z toggle).
export function fit(values, full = false) {
  const vs = values.filter((v) => Number.isFinite(v));
  if (vs.length === 0) return { lo: 0, hi: 100 };
  const min = Math.min(...vs);
  const max = Math.max(...vs);
  if (full) {
    return {
      lo: Math.floor((min * 0.5) / 10) * 10,
      hi: Math.ceil((max * 1.5) / 10) * 10,
    };
  }
  const pad = Math.max(4, (max - min) * 0.25);
  return { lo: min - pad, hi: max + pad };
}

// Stacking for labels that would collide: centers closer than
// LABEL_W columns apart drop to the next tier. Returns the handles
// sorted by column, each with `tier` added.
export function lanes(handles) {
  const lastCol = [];
  return [...handles].sort((a, b) => a.col - b.col).map((h) => {
    let tier = lastCol.findIndex((c) => h.col - c >= LABEL_W);
    if (tier === -1) tier = lastCol.length;
    lastCol[tier] = h.col;
    return { ...h, tier };
  });
}

// The plain-line checks of spec 6.4. Pay is the default direction:
// walk-away is the price ceiling, target the hoped-for price. A
// receive case flips the first check and rewords the third.
export function warnings({ target, alternative, walkaway, direction = "pay" }) {
  const t = Number(target);
  const a = Number(alternative);
  const w = Number(walkaway);
  const ok = (v) => Number.isFinite(v) && v > 0;
  const out = [];
  if (ok(t) && ok(w)) {
    if (direction === "receive" ? w > t : w < t) {
      const rel = direction === "receive" ? "above" : "below";
      out.push(`walk-away ${rel} target; the gate would block every offer hoped for`);
    }
    if (Math.abs(t - w) < 3) {
      out.push("target and walk-away less than $3 apart; little room to trade");
    }
  }
  if (ok(a) && ok(w) && a > w) {
    out.push(direction === "receive"
      ? "best alternative pays more than walk-away; consider raising it"
      : "best alternative costs more than walk-away; consider raising it");
  }
  return out;
}

// value <-> column over the bar. $1 steps (Math.round) and clamped to
// the range, so a drag can never land a handle outside it.
export function valueToX(v, lo, hi, cols) {
  const span = hi - lo;
  if (!(span > 0) || !(cols > 1)) return 0;
  return Math.max(0, Math.min(cols - 1, Math.round(((v - lo) / span) * (cols - 1))));
}

export function xToValue(x, lo, hi, cols) {
  const span = hi - lo;
  if (!(span > 0) || !(cols > 1)) return lo;
  const col = Math.max(0, Math.min(cols - 1, x));
  return Math.round(lo + (col / (cols - 1)) * span);
}

// Handle columns for the pointer hit test. An unset handle parks at
// the range's left edge, so grabbing it sets a value from nothing.
export function handleXs(values, lo, hi, cols, keys) {
  const xs = {};
  for (const k of keys) {
    const v = Number(values?.[k]);
    xs[k] = valueToX(Number.isFinite(v) && v > 0 ? v : lo, lo, hi, cols);
  }
  return xs;
}

// The nearest handle column within a 2-column grab radius, else null.
export function nearestHandle(x, positions) {
  let best = null;
  let dist = 3;
  for (const [key, col] of Object.entries(positions)) {
    const d = Math.abs(col - x);
    if (d < dist) {
      best = key;
      dist = d;
    }
  }
  return dist <= 2 ? best : null;
}

// The bar row as cells: the rail, the fixed offer marker O, then the
// handle marks. Each cell is {ch, handle}; callers color by handle.
export function barCells({ values, offer, lo, hi, cols, handles }) {
  const cells = Array.from({ length: cols }, () => ({ ch: "─" }));
  const put = (v, ch, handle) => {
    if (!Number.isFinite(v)) return;
    cells[valueToX(v, lo, hi, cols)] = { ch, handle };
  };
  put(offer, "O", "offer");
  for (const hd of handles) {
    const v = Number(values?.[hd.key]);
    put(Number.isFinite(v) && v > 0 ? v : null, hd.mark ?? "●", hd.key);
  }
  return cells;
}

// One label row as cells: every label centered on its column, then
// `leaders` fills still-blank columns with │. Labels win over
// leaders; leaders never overwrite text.
export function labelCells(items, leaders, cols) {
  const cells = Array.from({ length: cols }, () => ({ ch: " " }));
  for (const it of items) {
    const text = String(it.label);
    const room = Math.max(0, cols - text.length);
    const x = Math.max(0, Math.min(room, Math.round(it.col) - Math.floor(text.length / 2)));
    for (let i = 0; i < text.length; i++) cells[x + i] = { ch: text[i], color: it.color };
  }
  for (const col of leaders) {
    const x = Math.round(col);
    if (x >= 0 && x < cols && cells[x].ch === " ") cells[x] = { ch: "│", color: "gray" };
  }
  return cells;
}

// Cells to Text segments: runs of one color collapse into {text,
// color} so both the Client and the fallback draw one Text per row.
export function cellsText(cells) {
  const segs = [];
  for (const c of cells) {
    const last = segs[segs.length - 1];
    if (last && last.color === c.color) last.text += c.ch;
    else segs.push({ text: c.ch, color: c.color });
  }
  return segs;
}
