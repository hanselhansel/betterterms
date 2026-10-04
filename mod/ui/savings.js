// The savings tab (spec 6.5): total saved per year, a cumulative line
// chart by week and one bar per closed case, then a summary line.
// Svg draws on desktop, Raster in the terminal, and vscode and mobile
// fall back to plain text, matching the rest of the cockpit.
//
// Numbers come from `bt.py ledger total` for the aggregate and from
// the ledger.jsonl records it sums for the weekly and per-case views:
// the total command carries no per-week series, so the chart derives
// its own from the same records.

import * as IO from "../lib/hostio.js";

// ledger.jsonl lines -> records the chart needs. Junk lines skip.
export function parseRecords(text) {
  const out = [];
  for (const line of String(text ?? "").split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      const r = JSON.parse(line);
      const saved = Number(r?.saved_per_year);
      if (!r || typeof r.case_id !== "string" || !Number.isFinite(saved)) continue;
      out.push({ case_id: r.case_id, saved_per_year: saved, recorded_at: r.recorded_at ?? null });
    } catch { /* not json */ }
  }
  return out;
}

// ISO-8601 week of an ISO timestamp, "2026-W37". Records without
// recorded_at fall back to the date embedded in the case id.
export function isoWeek(iso, caseId) {
  let d = iso ? new Date(iso) : null;
  if (d === null || Number.isNaN(d.getTime())) {
    const m = /-(\d{4})(\d{2})(\d{2})-/.exec(String(caseId ?? ""));
    if (m === null) return "undated";
    d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  }
  const day = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dow = (day.getUTCDay() + 6) % 7;
  day.setUTCDate(day.getUTCDate() - dow + 3);
  const year = day.getUTCFullYear();
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const week = 1 + Math.round((day - jan4) / (7 * 86400000));
  return `${year}-W${String(week).padStart(2, "0")}`;
}

// The cumulative line: one point per week, oldest first.
export function weeks(records) {
  const buckets = new Map();
  for (const r of records) {
    const w = isoWeek(r.recorded_at, r.case_id);
    buckets.set(w, (buckets.get(w) ?? 0) + r.saved_per_year);
  }
  let cum = 0;
  return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b))
    .map(([week, sum]) => ({ week, sum, cum: (cum += sum) }));
}

// `bt ledger total` for the aggregate, ledger.jsonl for the series.
export async function savingsData(host, snap) {
  if (snap.home === null) return { total: null, records: [] };
  const lines = (await IO.readIf(host, `${snap.home}/ledger.jsonl`)) ?? "";
  const records = parseRecords(lines);
  let total = null;
  const bt = await IO.findBt(host);
  if (bt !== null) {
    const p = await IO.runProc(host, snap.home, ["python3", bt, "ledger", "total"]);
    try { total = JSON.parse(p?.stdout); } catch { total = null; }
  }
  if (total === null || typeof total !== "object") {
    total = {
      cases: records.length,
      by_currency: { USD: records.reduce((s, r) => s + r.saved_per_year, 0) },
    };
  }
  return { total, records };
}

const fmt = (v) => String(Math.round(v));

function chartModel(data) {
  const wks = weeks(data.records);
  const bars = data.records.map((r) => r.saved_per_year);
  const maxBar = Math.max(1, ...bars.map((v) => Math.abs(v)));
  const maxCum = Math.max(1, ...wks.map((w) => w.cum));
  return { wks, bars, maxBar, maxCum };
}

// The desktop chart: one rect per closed case, a polyline for the
// weekly cumulative, a baseline. Colors are muted, labels live in the
// summary line beneath.
function svgChart(data) {
  const { wks, bars, maxBar, maxCum } = chartModel(data);
  const W = 240;
  const H = 72;
  const top = 6;
  const bot = H - 8;
  const mid = top + (bot - top) / 2;
  const slot = bars.length ? (W - 20) / bars.length : 0;
  const rects = bars.map((v, i) => {
    const hh = (Math.abs(v) / maxBar) * ((bot - top) / 2 - 2);
    const x = 10 + i * slot + 1;
    const w = Math.max(2, slot - 2);
    return `<rect x="${x.toFixed(1)}" y="${v >= 0 ? mid - hh : mid}" width="${w.toFixed(1)}" ` +
      `height="${Math.max(1, hh).toFixed(1)}" fill="${v >= 0 ? "#4caf50" : "#e57373"}"/>`;
  }).join("");
  const pts = wks.map((w, i) => {
    const x = 10 + ((i + 0.5) / wks.length) * (W - 20);
    const y = bot - (w.cum / maxCum) * (bot - top - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const source =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}">` +
    `<line x1="10" y1="${mid}" x2="${W - 10}" y2="${mid}" stroke="#888" stroke-width="0.5"/>` +
    rects +
    (wks.length
      ? `<polyline points="${pts}" fill="none" stroke="#2196f3" stroke-width="1.5"/>`
      : "") +
    "</svg>";
  return {
    source,
    alt: `savings over ${wks.length} weeks, one bar per closed case`,
  };
}

const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

// Uint32Array -> standard padded base64, the cells format Raster
// takes. Node builtins are not part of the mod contract, so the
// encoder lives here.
export function u32base64(words) {
  const bytes = new Uint8Array(words.buffer, words.byteOffset, words.byteLength);
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const b0 = bytes[i];
    const b1 = i + 1 < bytes.length ? bytes[i + 1] : 0;
    const b2 = i + 2 < bytes.length ? bytes[i + 2] : 0;
    out += B64[b0 >> 2] + B64[((b0 & 3) << 4) | (b1 >> 4)];
    out += i + 1 < bytes.length ? B64[((b1 & 15) << 2) | (b2 >> 6)] : "=";
    out += i + 2 < bytes.length ? B64[b2 & 63] : "=";
  }
  return out;
}

// The terminal chart as a cell buffer of [codePoint, fg, bg]
// triplets: bars as block glyphs, the cumulative as a dotted line.
function rasterChart(data, cols, rows) {
  const { wks, bars, maxBar, maxCum } = chartModel(data);
  const area = new Uint32Array(cols * rows * 3);
  const DEF = 0x01000000;
  for (let i = 0; i < cols * rows; i++) {
    area[i * 3] = 0x20;
    area[i * 3 + 1] = DEF;
    area[i * 3 + 2] = DEF;
  }
  const set = (x, y, cp, fg) => {
    const i = (y * cols + x) * 3;
    area[i] = cp;
    area[i + 1] = fg;
    area[i + 2] = DEF;
  };
  const mid = Math.floor(rows / 2);
  bars.forEach((v, i) => {
    const x = Math.min(cols - 1, Math.floor(((i + 0.5) / bars.length) * cols));
    const hh = Math.round((Math.abs(v) / maxBar) * (rows / 2 - 1));
    for (let dy = 0; dy <= hh; dy++) {
      set(x, v >= 0 ? mid - dy : Math.min(rows - 1, mid + dy), 0x2588, v >= 0 ? 0x004caf50 : 0x00e57373);
    }
  });
  wks.forEach((w, i) => {
    const x = Math.min(cols - 1, Math.floor(((i + 0.5) / wks.length) * cols));
    const y = Math.max(0, Math.min(rows - 1, rows - 1 - Math.round((w.cum / maxCum) * (rows - 1))));
    set(x, y, 0x2022, 0x002196f3);
  });
  return u32base64(area);
}

export function savingsBody(el, data, surface) {
  const { Box, Text } = el;
  const rows = [];
  const byCurrency = data?.total?.by_currency ?? {};
  const keys = Object.keys(byCurrency);
  const total = keys.length
    ? keys.reduce((s, k) => s + (Number(byCurrency[k]) || 0), 0)
    : data.records.reduce((s, r) => s + r.saved_per_year, 0);
  const money = keys.length === 1 && keys[0] === "USD"
    ? `$${fmt(total)}`
    : keys.length
      ? keys.map((k) => `${k} ${fmt(byCurrency[k])}`).join(" · ")
      : `$${fmt(total)}`;
  rows.push(h(Text, { key: "sav-total" }, `saved ${money}/yr`));
  const m = chartModel(data);
  if (surface === "desktop" && el.Svg) {
    const { source, alt } = svgChart(data);
    rows.push(h(el.Svg, { source, alt, width: 240, height: 72 }));
  } else if (surface === "terminal" && el.Raster) {
    rows.push(h(el.Raster, {
      key: "sav-chart", columns: 40, rows: 8, cells: rasterChart(data, 40, 8),
    }));
  } else {
    for (const w of m.wks) {
      rows.push(h(Text, { key: `wk-${w.week}`, dimColor: true },
        `${w.week}  +$${fmt(w.sum)}  = $${fmt(w.cum)}`));
    }
  }
  const closed = data.records.length;
  const walked = data.records.filter((r) => !(r.saved_per_year > 0)).length;
  const avg = closed ? total / closed : 0;
  rows.push(h(Text, { key: "sav-sum", dimColor: true },
    `${closed} closed · ${walked} walked away · $${fmt(avg)}/yr average`));
  return h(Box, { key: "savings", flexDirection: "column" }, ...rows);
}
