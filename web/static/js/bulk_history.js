"use strict";
// bulk_history.js — /bulk/history results table

// ── Storage helpers ────────────────────────────────────────────
function getBulkHistory() {
  try { return JSON.parse(localStorage.getItem("pf_bulk_history") || "[]"); }
  catch { return []; }
}

// ── DOM ────────────────────────────────────────────────────────
const tbody     = document.getElementById("bh-tbody");
const emptyEl   = document.getElementById("bh-empty");
const searchEl  = document.getElementById("bh-search");
const statusSel = document.getElementById("bh-status-filter");
const sortSel   = document.getElementById("bh-sort");

// ── Summary strip ──────────────────────────────────────────────
function renderSummary() {
  const all  = getBulkHistory();
  const flat = all.flatMap(j => j.candidates || []);

  document.getElementById("bhs-jobs").textContent      = all.length;
  document.getElementById("bhs-total").textContent     = flat.length;
  document.getElementById("bhs-processed").textContent = flat.filter(c => c.status === "done").length;
  document.getElementById("bhs-failed").textContent    = flat.filter(c => c.status === "failed").length;

  const scores = flat.filter(c => c.confidence > 0).map(c => c.confidence);
  const avg    = scores.length ? scores.reduce((a,b)=>a+b,0)/scores.length : 0;
  document.getElementById("bhs-conf").textContent = scores.length
    ? Math.round(avg * 100) + "%" : "—";
}

// ── Main render ────────────────────────────────────────────────
function render() {
  renderSummary();

  const jobs = getBulkHistory();
  const q    = (searchEl?.value || "").toLowerCase().trim();
  const sf   = statusSel?.value || "all";
  const sort = sortSel?.value   || "date-desc";

  // Flatten candidates across all jobs, keeping job metadata
  let rows = jobs.flatMap(job =>
    (job.candidates || []).map(c => ({
      ...c,
      job_id: job.job_id,
      job_date: job.date,
    }))
  );

  // Filter
  if (q) {
    rows = rows.filter(r =>
      (r.name || "").toLowerCase().includes(q)   ||
      (r.email || "").toLowerCase().includes(q)  ||
      (r.job_id || "").toLowerCase().includes(q) ||
      (r.resume_name || "").toLowerCase().includes(q)
    );
  }
  if (sf !== "all") rows = rows.filter(r => r.status === sf);

  // Sort
  rows.sort((a, b) => {
    if (sort === "date-desc") return new Date(b.job_date) - new Date(a.job_date);
    if (sort === "date-asc")  return new Date(a.job_date) - new Date(b.job_date);
    if (sort === "name-asc")  return (a.name||"").localeCompare(b.name||"");
    if (sort === "conf-desc") return (b.confidence||0) - (a.confidence||0);
    return 0;
  });

  if (!rows.length) {
    if (tbody)   tbody.innerHTML = "";
    if (emptyEl) emptyEl.hidden  = false;
    return;
  }
  if (emptyEl) emptyEl.hidden = true;

  tbody.innerHTML = rows.map(r => {
    const c = r.confidence || 0;
    const p = Math.round(c * 100);
    const col = c >= 0.8 ? "#3a7d52" : c >= 0.6 ? "#b07d20" : "#963030";
    const dt  = new Date(r.job_date || r.processed_at || "");
    const dateStr = isNaN(dt) ? "—"
      : dt.toLocaleDateString("en-GB", { day:"numeric",month:"short",year:"numeric" });

    const statusMap = {
      done:           ["bh-badge--done",    "✓ Processed"],
      failed:         ["bh-badge--failed",  "✗ Failed"],
      resume_missing: ["bh-badge--missing", "⚠ No Resume"],
      csv_missing:    ["bh-badge--csv_missing","⚠ No CSV"],
    };
    const [scls, slabel] = statusMap[r.status] || ["", r.status];

    const matchColors = {
      email:"#5a90c8",phone:"#b07d20",exact_name:"#3a7d52",
      fuzzy_name:"#6b3f1f",regno:"#5a90c8",github:"#3a7d52",none:"#7a8fa8"
    };
    const mcol = matchColors[r.match_method] || "#7a8fa8";

    const key = JSON.stringify({job_id:r.job_id, index:r.index});
    const safeKey = btoa(key).replace(/=/g,"");

    return `
    <tr>
      <td class="bh-col-num">${r.index}</td>
      <td class="bh-col-name">
        <div class="bh-name" title="${esc(r.name)}">${esc(r.name)}</div>
        <div class="bh-email">${esc(r.email||"")}</div>
      </td>
      <td class="bh-col-resume" title="${esc(r.resume_name||"")}">${esc(r.resume_name||"—")}</td>
      <td class="bh-col-match"><span style="font-size:.7rem;color:${mcol};font-weight:700">${esc(r.match_method||"—")}</span></td>
      <td class="bh-col-status"><span class="bh-badge ${scls}">${slabel}</span></td>
      <td class="bh-col-conf">
        ${p > 0 ? `
          <div class="conf-wrap">
            <div class="conf-bar"><div class="conf-fill" style="width:${p}%;background:${col}"></div></div>
            <span class="conf-pct">${p}%</span>
          </div>` : '<span style="color:var(--dim)">—</span>'}
      </td>
      <td class="bh-col-date">${dateStr}</td>
      <td class="bh-col-actions">
        <div class="bh-actions">
          ${r.profile ? `<button class="bh-btn" onclick="viewProfile('${safeKey}')" title="View profile">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            View</button>` : ""}
          ${r.profile ? `<button class="bh-btn" onclick="downloadProfile('${safeKey}')" title="Download JSON">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            JSON</button>` : ""}
        </div>
      </td>
    </tr>`;
  }).join("");
}

// ── View / download ────────────────────────────────────────────
window._rowLookup = {};   // populated lazily

function _getRow(safeKey) {
  try {
    const key = JSON.parse(atob(safeKey));
    const jobs = getBulkHistory();
    const job  = jobs.find(j => j.job_id === key.job_id);
    return job?.candidates?.find(c => c.index === key.index) || null;
  } catch { return null; }
}

window.viewProfile = function(safeKey) {
  const r = _getRow(safeKey);
  if (!r?.profile) return;
  localStorage.setItem("pf_last_profile",  JSON.stringify(r.profile));
  localStorage.setItem("pf_last_warnings", JSON.stringify(r.warnings || []));
  window.location.href = "/profile";
};

window.downloadProfile = function(safeKey) {
  const r = _getRow(safeKey);
  if (!r?.profile) return;
  const blob = new Blob([JSON.stringify(r.profile, null, 2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${(r.name||"candidate").replace(/\s+/g,"_")}_profile.json`;
  a.click(); URL.revokeObjectURL(a.href);
};

// ── Clear all ──────────────────────────────────────────────────
document.getElementById("clear-bulk-btn")?.addEventListener("click", () => {
  if (!confirm("Clear all bulk history? This cannot be undone.")) return;
  localStorage.removeItem("pf_bulk_history");
  render();
});

// ── Event listeners ────────────────────────────────────────────
searchEl?.addEventListener("input",  render);
statusSel?.addEventListener("change", render);
sortSel?.addEventListener("change",   render);

function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

render();
