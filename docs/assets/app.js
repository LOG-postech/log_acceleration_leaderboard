"use strict";

// Data files resolve relative to the page so it works on GitHub Pages
// project sites (served under /<repo>/) and at the repo root alike.
const DATA_DIR = "./data";
const CAT_ORDER = ["short", "medium", "long"];

async function loadJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

const fmtMs = (v) => (v == null ? "—" : v >= 1000 ? (v / 1000).toFixed(2) + "s" : Math.round(v) + "ms");
const fmtSpeedup = (v) => (v == null ? "—" : v.toFixed(2) + "×");
const shortModel = (m) => (m ? String(m).split("/").pop() : "—");
const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function gateCell(gate) {
  const status = gate ? gate.status : "pending";
  const score = gate && gate.score != null ? gate.score.toFixed(3) : "—";
  const thr = gate && gate.threshold != null ? gate.threshold.toFixed(3) : "—";
  const sym = status === "pass" ? "✅" : status === "fail" ? "❌" : "⏳";
  return `<span class="gate ${status}" title="${status} — score ${score} / threshold ${thr}">${sym}</span>`;
}

function qualityStatusOf(row) {
  const vals = Object.values(row.quality || {});
  if (vals.some((g) => g && g.status === "fail")) return "fail";
  if (vals.length && vals.every((g) => g && g.status === "pass")) return "pass";
  return "pending";
}

const gateKeysOf = (cfg) => Object.keys(cfg.quality_gates || {}).filter((k) => k !== "_comment");

// Columns. `showGpu` / `showModel` add those columns (used on the flat
// submissions page). Boards omit both (GPU is the board, model is the tab).
function buildCols(cfg, o) {
  const cols = [];
  if (o.showRank) cols.push({ key: "rank", label: "#" });
  cols.push({ key: "team", label: "Team / Submission", left: true });
  cols.push({ key: "submitter", label: "By", left: true });
  if (o.showGpu) cols.push({ key: "gpu", label: "GPU" });
  if (o.showModel) cols.push({ key: "model", label: "Model", left: true });
  cols.push({ key: "avg_speedup", label: "Avg Speedup" });
  for (const cat of CAT_ORDER) cols.push({ key: `lat.${cat}`, label: cfg.latency.categories[cat].label });
  for (const gk of gateKeysOf(cfg)) cols.push({ key: `q.${gk}`, label: cfg.quality_gates[gk].label });
  cols.push({ key: "date", label: "Date" });
  return cols;
}

function rowHTML(row, cfg, o) {
  let c = "";
  if (o.showRank) {
    const r = row.rank;
    const rc = r === 1 ? "r1" : r === 2 ? "r2" : r === 3 ? "r3" : "";
    c += `<td class="rank ${rc}">${r ?? "—"}</td>`;
  }
  const example = row.example ? `<span class="example-flag">example</span>` : "";
  c += `<td class="left"><div class="team-name">${escapeHtml(row.team || "—")}${example}</div>` +
       `<div class="sub-name">${escapeHtml(row.display_name || row.submission_id || "")}</div></td>`;
  c += `<td class="left submitter">${escapeHtml(row.submitter || "—")}</td>`;
  if (o.showGpu) c += `<td><span class="gpu-pill">${escapeHtml(row.gpu || "?")}</span></td>`;
  if (o.showModel) c += `<td class="left"><span class="gpu-pill" title="${escapeHtml(row.model || "")}">${escapeHtml(shortModel(row.model))}</span></td>`;
  c += `<td><span class="speedup ${row.avg_speedup == null ? "none" : ""}">${fmtSpeedup(row.avg_speedup)}</span></td>`;
  for (const cat of CAT_ORDER) {
    const cc = (row.latency || {})[cat] || {};
    c += `<td><span class="ms">${fmtMs(cc.median_ms)}</span><br><span class="sub-speedup">${fmtSpeedup(cc.speedup)}</span></td>`;
  }
  for (const gk of gateKeysOf(cfg)) c += `<td>${gateCell((row.quality || {})[gk])}</td>`;
  c += `<td class="submitter">${escapeHtml(row.date || "—")}</td>`;
  return c;
}

function sortValue(row, key) {
  if (key === "avg_speedup") return row.avg_speedup ?? -Infinity;
  if (key === "rank") return row.rank ?? Infinity;
  if (key.startsWith("lat.")) return ((row.latency || {})[key.slice(4)] || {}).median_ms ?? Infinity;
  if (key.startsWith("q.")) {
    const g = (row.quality || {})[key.slice(2)];
    return g && g.score != null ? g.score : -Infinity;
  }
  return String(row[key] ?? "").toLowerCase();
}

const STRING_COLS = new Set(["team", "submitter", "gpu", "model", "date"]);

// Build a sortable table inside mountEl. Returns { setRows } to swap data.
function renderTable(mountEl, rows, cfg, o) {
  const scroll = document.createElement("div");
  scroll.className = "table-scroll";
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tbody = document.createElement("tbody");
  table.append(thead, tbody);
  scroll.appendChild(table);
  mountEl.appendChild(scroll);

  const cols = buildCols(cfg, o);
  thead.innerHTML = `<tr>${cols
    .map((c) => `<th data-key="${c.key}" class="${c.left ? "left" : ""}">${escapeHtml(c.label)}</th>`)
    .join("")}</tr>`;

  let cur = rows.slice();
  let sortKey = o.defaultSortKey || "avg_speedup";
  let asc = !!o.defaultAsc;

  function draw() {
    const arr = cur.slice().sort((a, b) => {
      const va = sortValue(a, sortKey), vb = sortValue(b, sortKey);
      return va < vb ? (asc ? -1 : 1) : va > vb ? (asc ? 1 : -1) : 0;
    });
    tbody.innerHTML = arr.length
      ? arr
          .map((r) => {
            const q = r.quality_status || qualityStatusOf(r);
            const cls = q === "fail" || r.valid === false ? ' class="invalid"' : "";
            return `<tr${cls}>${rowHTML(r, cfg, o)}</tr>`;
          })
          .join("")
      : `<tr><td class="empty" colspan="${cols.length}">No submissions yet.</td></tr>`;
    thead.querySelectorAll("th").forEach((th) => {
      th.classList.toggle("sorted", th.dataset.key === sortKey);
      th.classList.toggle("asc", th.dataset.key === sortKey && asc);
    });
  }

  thead.querySelectorAll("th").forEach((th) =>
    th.addEventListener("click", () => {
      const k = th.dataset.key;
      if (sortKey === k) asc = !asc;
      else { sortKey = k; asc = STRING_COLS.has(k); }
      draw();
    })
  );
  draw();
  return { setRows: (n) => { cur = n.slice(); draw(); } };
}

function baselineNote(cfg, gpu, model) {
  const b = ((cfg.baselines || {})[model] || {})[gpu];
  if (b && CAT_ORDER.every((c) => b[c] != null)) {
    return `baseline (dense): ${CAT_ORDER.map((c) => `${b[c]}ms`).join(" / ")}`;
  }
  return `⚠ baseline not calibrated — run the dense image with <code>--baseline</code> (speedups show as —)`;
}

// Union of models declared in config (ordered) + any present in the data.
function modelList(cfg, data) {
  const inData = (data.submissions || []).map((r) => r.model).filter(Boolean);
  return Array.from(new Set([...(cfg.models || []), ...inData]));
}

function renderModelTabs(el, models, active, onSelect) {
  if (!el) return;
  el.innerHTML = models
    .map((m) => `<button class="subtab ${m === active ? "active" : ""}" data-model="${escapeHtml(m)}">${escapeHtml(shortModel(m))}</button>`)
    .join("");
  el.querySelectorAll(".subtab").forEach((b) => b.addEventListener("click", () => onSelect(b.dataset.model)));
}

// Client-side GPU board order (mirrors runner/update_results.GPU_ORDER).
const GPU_ORDER = ["A100", "PRO6000", "RTX3090"];
function cmpGpu(a, b) {
  const ia = GPU_ORDER.indexOf(a), ib = GPU_ORDER.indexOf(b);
  const ra = ia === -1 ? GPU_ORDER.length : ia, rb = ib === -1 ? GPU_ORDER.length : ib;
  return ra - rb || (a < b ? -1 : a > b ? 1 : 0);
}

// One board (GPU title + baseline note + table). With showRank the table is a
// ranking (leaderboard); without it, it lists every run (submissions view).
function boardSection(boardsEl, gpu, model, rows, cfg, opts) {
  const showRank = !opts || opts.showRank !== false;
  const sec = document.createElement("section");
  sec.className = "board";
  const head = document.createElement("div");
  head.className = "board-head";
  head.innerHTML =
    `<h2 class="board-title">${escapeHtml(gpu)}</h2>` +
    `<div class="board-note">${baselineNote(cfg, gpu, model)}</div>`;
  sec.appendChild(head);
  const mount = document.createElement("div");
  sec.appendChild(mount);
  boardsEl.appendChild(sec);
  renderTable(mount, rows || [], cfg, {
    showRank, showGpu: false, showModel: false,
    defaultSortKey: showRank ? "rank" : "avg_speedup",
    defaultAsc: showRank,
  });
}

async function main() {
  let cfg, data;
  try {
    [cfg, data] = await Promise.all([loadJSON(`${DATA_DIR}/config.json`), loadJSON(`${DATA_DIR}/results.json`)]);
  } catch (e) {
    const t = document.getElementById("boards") || document.getElementById("subs");
    if (t) t.innerHTML = `<div class="empty">Failed to load data: ${escapeHtml(e.message)}</div>`;
    return;
  }

  document.querySelectorAll("[data-cfg-title]").forEach((el) => (el.textContent = cfg.title));
  document.querySelectorAll("[data-cfg-subtitle]").forEach((el) => (el.textContent = cfg.subtitle || ""));
  const updatedEl = document.getElementById("updated");
  if (updatedEl && data.updated) updatedEl.textContent = "Updated " + data.updated.replace("T", " ").replace("Z", " UTC");

  const models = modelList(cfg, data);
  const tabsEl = document.getElementById("model-tabs");

  // Leaderboard page: model sub-tabs → per-GPU boards for the active model.
  const boardsEl = document.getElementById("boards");
  if (boardsEl) {
    const groups = data.groups || [];
    let active = models[0] || null;
    function draw() {
      renderModelTabs(tabsEl, models, active, (m) => { active = m; draw(); });
      const gs = groups.filter((g) => g.model === active);
      boardsEl.innerHTML = "";
      if (!gs.length) {
        boardsEl.innerHTML = `<div class="empty">No submissions yet for ${escapeHtml(shortModel(active || ""))}.</div>`;
        return;
      }
      for (const g of gs) boardSection(boardsEl, g.gpu, g.model, g.rows, cfg);
    }
    draw();
    return;
  }

  // Submissions page: model sub-tabs → per-GPU boards showing EVERY run
  // (same look as the leaderboard, but no best-per-team dedup and no rank).
  const subsEl = document.getElementById("subs");
  if (!subsEl) return;
  const rowsAll = data.submissions || [];
  let activeModel = models[0] || null;
  function draw() {
    renderModelTabs(tabsEl, models, activeModel, (m) => { activeModel = m; draw(); });
    const forModel = rowsAll.filter((r) => r.model === activeModel);
    const byGpu = new Map();
    for (const r of forModel) {
      const g = r.gpu || "?";
      if (!byGpu.has(g)) byGpu.set(g, []);
      byGpu.get(g).push(r);
    }
    subsEl.innerHTML = "";
    const gpus = Array.from(byGpu.keys()).sort(cmpGpu);
    if (!gpus.length) {
      subsEl.innerHTML = `<div class="empty">No submissions yet for ${escapeHtml(shortModel(activeModel || ""))}.</div>`;
      return;
    }
    for (const g of gpus) boardSection(subsEl, g, activeModel, byGpu.get(g), cfg, { showRank: false });
  }
  draw();
}

main();
