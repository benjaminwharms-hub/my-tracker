"use strict";

/* =========================================================
   Helpers
   ========================================================= */

const $ = (sel) => document.querySelector(sel);
const DAY_MS = 864e5;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };

const fmt = (n, digits = 0) => n.toLocaleString("en-US", {
  minimumFractionDigits: digits, maximumFractionDigits: digits
});

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// Dates are kept as local dates ("2026-11-19" → midnight local), never UTC,
// so a weigh-in never slips into the wrong day or week.
const toDate = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const isoDate = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const mondayOf = (d) => addDays(d, -((d.getDay() + 6) % 7));
const today = () => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), n.getDate()); };

const longDate = (d) => d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
const shortDate = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });

/* =========================================================
   CSV loading (handles quoted fields with commas in them)
   ========================================================= */

function parseCSV(text) {
  text = text.replace(/^﻿/, "");
  const rows = [];
  let row = [], field = "", quoted = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') {
      quoted = true;
    } else if (c === ",") {
      row.push(field); field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row);
      row = []; field = "";
    } else {
      field += c;
    }
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }

  const [head, ...body] = rows.filter((r) => r.some((x) => x.trim() !== ""));
  if (!head) return [];
  const keys = head.map((h) => h.trim());
  return body.map((r) => Object.fromEntries(keys.map((k, i) => [k, (r[i] ?? "").trim()])));
}

async function loadCSV(name) {
  try {
    const res = await fetch(`data/${name}.csv`, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    return parseCSV(await res.text());
  } catch {
    return null; // shown as a notice; the rest of the page still works
  }
}

/* =========================================================
   Data shaping
   ========================================================= */

function buildWeights(rows) {
  return rows
    .filter((r) => /^\d{4}-\d{2}-\d{2}$/.test(r.date) && num(r.weight) > 0)
    .map((r) => ({ date: r.date, d: toDate(r.date), w: num(r.weight), note: r.note || "" }))
    .sort((a, b) => a.d - b.d);
}

// Monday-to-Sunday weeks, newest first.
function buildWeeks(weights) {
  const byWeek = new Map();
  for (const p of weights) {
    const key = isoDate(mondayOf(p.d));
    if (!byWeek.has(key)) byWeek.set(key, []);
    byWeek.get(key).push(p.w);
  }
  return [...byWeek.entries()]
    .map(([key, vals]) => ({ key, start: toDate(key), avg: vals.reduce((a, b) => a + b, 0) / vals.length, n: vals.length }))
    .sort((a, b) => b.start - a.start);
}

const weekFor = (weeks, monday) => weeks.find((w) => w.key === isoDate(monday));

const MACROS = ["calories", "protein", "carbs", "fat", "fiber", "sodium"];

// Meal names start with a number for ordering: "1 · Breakfast".
const mealOrder = (name) => { const m = /^(\d+)/.exec(name); return m ? +m[1] : 999; };
const mealLabel = (name) => name.replace(/^\d+\s*·\s*/, "");

// One entry per day, newest first, with meals in order and day totals.
function buildDays(rows) {
  const byDay = new Map();
  for (const r of rows) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date)) continue;
    if (!byDay.has(r.date)) byDay.set(r.date, []);
    byDay.get(r.date).push(r);
  }
  return [...byDay.entries()]
    .map(([date, meals]) => {
      meals.sort((a, b) => mealOrder(a.meal) - mealOrder(b.meal) || a.meal.localeCompare(b.meal));
      const totals = Object.fromEntries(MACROS.map((k) => [k, meals.reduce((s, m) => s + num(m[k]), 0)]));
      return { date, d: toDate(date), meals, totals };
    })
    .sort((a, b) => b.d - a.d);
}

function dayStatus(t) {
  const T = CONFIG.targets, S = CONFIG.status;
  if (t.calories < T.calories - S.underBy) return ["Under", "bad"];
  if (t.calories > T.calories + S.overBy) return ["Over", "warn"];
  if (t.protein < T.protein * S.lowProtein) return ["Low protein", "bad"];
  if (t.protein < T.protein * S.proteinShort) return ["Protein short", "warn"];
  return ["On target", "good"];
}

/* =========================================================
   Header + tiles
   ========================================================= */

function renderHeader() {
  const T = CONFIG.targets;
  $("#name").textContent = `${CONFIG.name}'s Tracker`;
  $("#targets-line").textContent =
    `${fmt(T.calories)} kcal · ${T.protein} g protein · ${T.carbs} g carbs · ${T.fat} g fat · goal ${CONFIG.goalWeight} ${CONFIG.units}`;
}

function weekSentence(weeks) {
  const u = CONFIG.units;
  const thisMon = mondayOf(today());
  const tw = weekFor(weeks, thisMon);
  const lw = weekFor(weeks, addDays(thisMon, -7));

  if (!weeks.length) return "No weigh-ins logged yet.";
  if (!tw && !lw) return `No weigh-ins in the last two weeks. Your last logged week averaged <b>${fmt(weeks[0].avg, 1)} ${u}</b>.`;
  if (!tw) return `No weigh-ins yet this week. Last week averaged <b>${fmt(lw.avg, 1)} ${u}</b>.`;
  if (!lw) return `This week you're averaging <b>${fmt(tw.avg, 1)} ${u}</b> from ${plural(tw.n, "weigh-in")}. No weigh-ins last week to compare against.`;

  const diff = tw.avg - lw.avg;
  const change = Math.abs(diff) < 0.05 ? "the same as"
    : `${diff > 0 ? "up" : "down"} <b>${fmt(Math.abs(diff), 1)} ${u}</b> from`;
  return `This week you're averaging <b>${fmt(tw.avg, 1)} ${u}</b>, ${change} last week's ${fmt(lw.avg, 1)} ${u}.`;
}

function tile(label, value, sub) {
  return `<div class="tile"><span class="label">${label}</span><span class="value">${value}</span><span class="sub">${sub}</span></div>`;
}

function renderTiles(weights, weeks, days) {
  const u = CONFIG.units;
  const latest = weights[weights.length - 1];
  const thisMon = mondayOf(today());
  const tw = weekFor(weeks, thisMon);
  const lw = weekFor(weeks, addDays(thisMon, -7));

  const html = [];

  html.push(latest
    ? tile("Latest weigh-in", `${fmt(latest.w, 1)} <small>${u}</small>`, longDate(latest.d))
    : tile("Latest weigh-in", "—", "Nothing logged yet"));

  html.push(tile("This week (Mon–Sun)",
    tw ? `${fmt(tw.avg, 1)} <small>${u}</small>` : "—",
    lw ? `Last week ${fmt(lw.avg, 1)} ${u}` : "Last week —"));

  if (latest) {
    const left = CONFIG.goalWeight - latest.w;
    html.push(Math.abs(left) < 0.5
      ? tile("Left to goal", "Done", `At ${CONFIG.goalWeight} ${u}`)
      : tile("Left to goal", `${fmt(Math.abs(left), 1)} <small>${u}</small>`,
          `to ${left > 0 ? "gain" : "lose"} to reach ${CONFIG.goalWeight}`));
  } else {
    html.push(tile("Left to goal", "—", `Goal ${CONFIG.goalWeight} ${u}`));
  }

  const recent = days.slice(0, 7);
  if (recent.length) {
    const avg = (k) => recent.reduce((s, d) => s + d.totals[k], 0) / recent.length;
    html.push(tile(`Avg, last ${plural(recent.length, "logged day")}`,
      `${fmt(avg("calories"))} <small>kcal</small>`,
      `${fmt(avg("protein"))} g protein`));
  } else {
    html.push(tile("Avg, last 7 logged days", "—", "No meals logged yet"));
  }

  $("#tiles").innerHTML = html.join("");
}

/* =========================================================
   Weight chart (plain SVG, redrawn at the real width)
   ========================================================= */

let chartZoomed = false;

function renderChart(weights) {
  const box = $("#chart");
  if (!weights.length) {
    box.innerHTML = `<p class="empty">Log a weigh-in to see the chart.</p>`;
    return;
  }

  const width = Math.max(260, box.clientWidth);
  const height = 240;
  const pad = { l: 38, r: 12, t: 14, b: 26 };
  const [bandLo, bandHi] = CONFIG.goalBand;
  const ws = weights.map((p) => p.w);

  // Y range: include the goal band unless zoomed in on the data.
  let lo = Math.min(...ws), hi = Math.max(...ws);
  if (!chartZoomed) { lo = Math.min(lo, bandLo); hi = Math.max(hi, bandHi); }
  const span = hi - lo;
  const step = span > 30 ? 10 : span > 8 ? 5 : span > 3 ? 2 : 1;
  lo = Math.floor((lo - step * 0.25) / step) * step;
  hi = Math.ceil((hi + step * 0.25) / step) * step;

  // X range: real dates, padded to at least a week so one point isn't on the edge.
  let t0 = weights[0].d.getTime(), t1 = weights[weights.length - 1].d.getTime();
  if (t1 - t0 < 6 * DAY_MS) { const mid = (t0 + t1) / 2; t0 = mid - 3.5 * DAY_MS; t1 = mid + 3.5 * DAY_MS; }

  const x = (t) => pad.l + ((t - t0) / (t1 - t0)) * (width - pad.l - pad.r);
  const y = (v) => pad.t + ((hi - v) / (hi - lo)) * (height - pad.t - pad.b);

  const parts = [];

  // Goal band
  const bTop = Math.max(lo, Math.min(hi, bandHi)), bBot = Math.max(lo, Math.min(hi, bandLo));
  if (bTop > bBot) {
    parts.push(`<rect class="band" x="${pad.l}" y="${y(bTop)}" width="${width - pad.l - pad.r}" height="${y(bBot) - y(bTop)}"/>`);
    parts.push(`<text class="band-label" x="${width - pad.r - 4}" y="${y(bTop) + 13}" text-anchor="end">Goal ${bandLo}–${bandHi}</text>`);
  }

  // Grid + y labels
  const grid = [], axis = [];
  for (let v = lo; v <= hi + 1e-9; v += step) {
    grid.push(`<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(v)}" y2="${y(v)}"/>`);
    axis.push(`<text x="${pad.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`);
  }
  // X labels: up to 4 evenly spaced dates
  const ticks = Math.min(4, Math.max(2, Math.floor((width - pad.l) / 90)));
  for (let i = 0; i < ticks; i++) {
    const t = t0 + ((t1 - t0) * i) / (ticks - 1);
    const anchor = i === 0 ? "start" : i === ticks - 1 ? "end" : "middle";
    axis.push(`<text x="${x(t)}" y="${height - 6}" text-anchor="${anchor}">${shortDate(new Date(t))}</text>`);
  }
  parts.unshift(`<g class="grid">${grid.join("")}</g>`);
  parts.push(`<g class="axis">${axis.join("")}</g>`);

  // Line + dots, latest highlighted
  const pts = weights.map((p) => ({ ...p, px: x(p.d.getTime()), py: y(p.w) }));
  if (pts.length > 1) parts.push(`<polyline class="line" points="${pts.map((p) => `${p.px},${p.py}`).join(" ")}"/>`);
  pts.slice(0, -1).forEach((p) => parts.push(`<circle class="dot" cx="${p.px}" cy="${p.py}" r="3.5"/>`));
  const last = pts[pts.length - 1];
  parts.push(`<circle class="latest-ring" cx="${last.px}" cy="${last.py}" r="10"/>`);
  parts.push(`<circle class="latest" cx="${last.px}" cy="${last.py}" r="6"/>`);
  parts.push(`<circle class="focus" r="8" cx="-99" cy="-99"/>`);

  box.innerHTML =
    `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="Weight over time">${parts.join("")}</svg>` +
    `<div class="tip" hidden></div>`;

  // Tooltip: tap or hover anywhere on the chart to see the nearest weigh-in.
  const svg = box.querySelector("svg"), tip = box.querySelector(".tip"), focus = box.querySelector(".focus");
  const show = (e) => {
    const r = svg.getBoundingClientRect();
    const mx = (e.clientX - r.left) * (width / r.width);
    const p = pts.reduce((best, q) => (Math.abs(q.px - mx) < Math.abs(best.px - mx) ? q : best));
    focus.setAttribute("cx", p.px); focus.setAttribute("cy", p.py);
    tip.innerHTML = `${longDate(p.d)}<br><b>${fmt(p.w, 1)} ${CONFIG.units}</b>${p.note ? `<br>${esc(p.note)}` : ""}`;
    tip.hidden = false;
    const scale = r.width / width;
    const tipW = tip.offsetWidth;
    const left = Math.min(Math.max(p.px * scale, tipW / 2), r.width - tipW / 2);
    tip.style.left = `${left}px`;
    tip.style.top = `${p.py * scale}px`;
  };
  const hide = () => { tip.hidden = true; focus.setAttribute("cx", -99); };
  svg.addEventListener("pointerdown", show);
  svg.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse") show(e); });
  svg.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") hide(); });
  document.addEventListener("pointerdown", (e) => { if (!svg.contains(e.target)) hide(); });
}

/* =========================================================
   Tables + day list
   ========================================================= */

function renderWeeks(weeks) {
  if (!weeks.length) { $("#weeks").innerHTML = `<p class="empty">No weigh-ins yet.</p>`; return; }
  const rows = weeks.map((w, i) => {
    const prev = weeks[i + 1];
    const diff = prev ? w.avg - prev.avg : null;
    const change = diff === null ? "—" : `${diff > 0 ? "+" : diff < 0 ? "−" : ""}${fmt(Math.abs(diff), 1)}`;
    return `<tr><td>${shortDate(w.start)}</td><td class="n">${fmt(w.avg, 1)}</td><td class="n">${change}</td><td class="n">${w.n}</td></tr>`;
  });
  $("#weeks").innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Week of</th><th class="n">Average</th><th class="n">Change</th><th class="n">Weigh-ins</th></tr></thead>
    <tbody>${rows.join("")}</tbody></table></div>`;
}

function macroLine(m) {
  return `${fmt(num(m.protein))} P · ${fmt(num(m.carbs))} C · ${fmt(num(m.fat))} F · ${fmt(num(m.fiber))} fibre · ${fmt(num(m.sodium))} mg sodium`;
}

function renderDays(days) {
  if (!days.length) { $("#days").innerHTML = `<p class="empty">No meals logged yet.</p>`; return; }
  const todayIso = isoDate(today());

  $("#days").innerHTML = days.map((day) => {
    const t = day.totals;
    const isToday = day.date === todayIso;
    let [label, cls] = dayStatus(t);
    // Today isn't over yet, so being under on calories just means "keep eating".
    if (isToday && label === "Under") [label, cls] = ["So far", "neutral"];
    const name = isToday ? `Today · ${shortDate(day.d)}` : longDate(day.d);

    const meals = day.meals.map((m) => {
      // Items are separated by ";" in meals.csv, e.g. "3 eggs; 2 toast; coffee"
      const items = m.items.split(";").map((s) => s.trim()).filter(Boolean);
      return `<div class="meal">
        <h3><span>${esc(mealLabel(m.meal))}</span><span class="num">${fmt(num(m.calories))} kcal</span></h3>
        ${items.length ? `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : ""}
        <div class="m">${macroLine(m)}</div>
      </div>`;
    }).join("");

    return `<details class="day">
      <summary>
        <div class="day-head"><span class="day-date">${name}</span><span class="pill ${cls}">${label}</span></div>
        <div class="macros">
          <div><span>Calories</span><b>${fmt(t.calories)}</b></div>
          <div><span>Protein</span><b>${fmt(t.protein)} g</b></div>
          <div><span>Carbs</span><b>${fmt(t.carbs)} g</b></div>
          <div><span>Fat</span><b>${fmt(t.fat)} g</b></div>
          <div><span>Fibre</span><b>${fmt(t.fiber)} g</b></div>
          <div><span>Sodium</span><b>${fmt(t.sodium)} mg</b></div>
        </div>
      </summary>
      <div class="meals">${meals}</div>
    </details>`;
  }).join("");
}

// Estimated one-rep max (Epley): weight × (1 + reps ÷ 30)
const e1rm = (w, r) => (r <= 1 ? w : w * (1 + r / 30));

function renderLifts(rows) {
  const lifts = rows
    .filter((r) => /^\d{4}-\d{2}-\d{2}$/.test(r.date) && r.lift)
    .map((r) => ({ ...r, d: toDate(r.date), w: num(r.weight), reps: num(r.reps) }))
    .sort((a, b) => b.d - a.d);

  if (!lifts.length) { $("#lifts").innerHTML = `<p class="empty">No lifts logged yet.</p>`; return; }

  const body = lifts.map((l) => `<tr>
      <td>${shortDate(l.d)}</td><td>${esc(l.lift)}</td>
      <td class="n">${fmt(l.w, l.w % 1 ? 1 : 0)}</td><td class="n">${fmt(l.reps)}</td>
      <td class="n">${fmt(e1rm(l.w, l.reps))}</td><td>${esc(l.gym)}</td></tr>`).join("");

  $("#lifts").innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Lift</th><th class="n">Weight</th><th class="n">Reps</th><th class="n">Est. max</th><th>Gym</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
}

/* =========================================================
   Start
   ========================================================= */

async function main() {
  renderHeader();

  const [weightRows, mealRows, liftRows] = await Promise.all(["weights", "meals", "lifts"].map(loadCSV));
  const failed = ["weights", "meals", "lifts"].filter((_, i) => [weightRows, mealRows, liftRows][i] === null);
  if (failed.length) {
    $("#notice").textContent = `Couldn't load ${failed.join(", ")}.csv. Check your connection and refresh.`;
    $("#notice").hidden = false;
  }

  const weights = buildWeights(weightRows || []);
  const weeks = buildWeeks(weights);
  const days = buildDays(mealRows || []);

  $("#week-sentence").innerHTML = weekSentence(weeks);
  renderTiles(weights, weeks, days);
  renderChart(weights);
  renderWeeks(weeks);
  renderDays(days);
  renderLifts(liftRows || []);

  $("#zoom").addEventListener("click", (e) => {
    chartZoomed = !chartZoomed;
    e.currentTarget.textContent = chartZoomed ? "Show goal band" : "Zoom to my weights";
    renderChart(weights);
  });

  // Redraw the chart at the new width when the phone rotates.
  let lastW = $("#chart").clientWidth, timer;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const w = $("#chart").clientWidth;
      if (w !== lastW) { lastW = w; renderChart(weights); }
    }, 150);
  });
}

main();
