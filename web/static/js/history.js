"use strict";

// ── Storage helpers ────────────────────────────────────────────
function getHistory() {
  try { return JSON.parse(localStorage.getItem("pf_history") || "[]"); }
  catch { return []; }
}
function saveHistory(h) { localStorage.setItem("pf_history", JSON.stringify(h)); }

// Called after every successful pipeline run to save the entry
window.pfSaveHistory = function(profile, warnings) {
  const h = getHistory();
  const name = (profile.name?.value || profile.full_name?.value || "Unknown").toString();
  const conf = avgConfidence(profile);
  const entry = {
    id:        profile.candidate_id || crypto.randomUUID(),
    name,
    date:      new Date().toISOString(),
    confidence: conf,
    status:    warnings?.length > 0 ? "warn" : "ok",
    warnings:  warnings || [],
    profile,
  };
  h.unshift(entry);
  // Keep last 100
  if (h.length > 100) h.splice(100);
  saveHistory(h);
};

function avgConfidence(profile) {
  const fields = ["full_name","name","emails","phones","skills","location","years_experience","links"];
  const scores = fields.map(k => profile[k]?.confidence).filter(v => v != null);
  if (!scores.length) return 0;
  return scores.reduce((a, b) => a + b, 0) / scores.length;
}

// ── Render ─────────────────────────────────────────────────────
const tbody     = document.getElementById("hist-tbody");
const emptyEl   = document.getElementById("hist-empty");
const tableWrap = document.getElementById("hist-table-wrap");
const summary   = document.getElementById("hist-summary");
const searchInput = document.getElementById("hist-search-input");
const sortSel   = document.getElementById("hist-sort");
const statusSel = document.getElementById("hist-status-filter");

function confColor(c) {
  if (c >= 0.8) return "#3a7d52";
  if (c >= 0.6) return "#b07d20";
  return "#963030";
}

function render() {
  let data = getHistory();

  // Filter
  const q = searchInput.value.toLowerCase().trim();
  if (q) {
    data = data.filter(e => {
      const str = JSON.stringify(e.profile).toLowerCase();
      return e.name.toLowerCase().includes(q) || str.includes(q);
    });
  }
  const sf = statusSel.value;
  if (sf !== "all") data = data.filter(e => e.status === sf);

  // Sort
  const sort = sortSel.value;
  data.sort((a, b) => {
    if (sort === "date-desc") return new Date(b.date) - new Date(a.date);
    if (sort === "date-asc")  return new Date(a.date) - new Date(b.date);
    if (sort === "name-asc")  return a.name.localeCompare(b.name);
    if (sort === "conf-desc") return b.confidence - a.confidence;
    if (sort === "conf-asc")  return a.confidence - b.confidence;
    return 0;
  });

  // Summary
  const all = getHistory();
  summary.innerHTML = [
    { label:"Total Profiles",  value: all.length },
    { label:"Passed Validation", value: all.filter(e => e.status === "ok").length },
    { label:"Avg Confidence",  value: all.length ? Math.round(all.reduce((a,e) => a + e.confidence, 0) / all.length * 100) + "%" : "—" },
  ].map(s => `
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 16px;display:flex;gap:10px;align-items:center;">
      <span style="font-size:1.1rem;font-weight:800;color:var(--text);">${s.value}</span>
      <span style="font-size:.75rem;color:var(--dim);">${s.label}</span>
    </div>`).join("");

  if (data.length === 0) {
    tbody.innerHTML = "";
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  tbody.innerHTML = data.map(e => {
    const c = e.confidence;
    const dt = new Date(e.date);
    const dateStr = dt.toLocaleDateString("en-GB", { day:"numeric", month:"short", year:"numeric" });
    const timeStr = dt.toLocaleTimeString("en-GB", { hour:"2-digit", minute:"2-digit" });
    return `
    <tr data-id="${e.id}">
      <td>
        <div class="hist-name">${esc(e.name)}</div>
        <div class="hist-id">${esc(e.id.slice(0, 8))}…</div>
      </td>
      <td>
        <div>${dateStr}</div>
        <div style="font-size:.75rem;color:var(--dim);">${timeStr}</div>
      </td>
      <td>
        <span class="hist-conf-bar"><span class="hist-conf-fill" style="width:${c*100}%;background:${confColor(c)}"></span></span>
        <span style="font-size:.82rem;color:var(--muted);">${Math.round(c*100)}%</span>
      </td>
      <td>
        <span style="font-size:.75rem;color:var(--dim);">CSV + Resume</span>
      </td>
      <td>
        <span class="hist-status hist-status--${e.status}">
          ${e.status === "ok" ? "✓ Passed" : "⚠ Warnings"}
        </span>
      </td>
      <td>
        <div class="hist-actions">
          <button class="hist-action-btn" onclick="viewProfile('${e.id}')" title="View profile">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            View
          </button>
          <button class="hist-action-btn" onclick="downloadEntry('${e.id}')" title="Download JSON">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            JSON
          </button>
          <button class="hist-action-btn hist-action-btn--danger" onclick="deleteEntry('${e.id}')" title="Delete">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
          </button>
        </div>
      </td>
    </tr>`;
  }).join("");
}

function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

window.viewProfile = function(id) {
  const h = getHistory();
  const e = h.find(x => x.id === id);
  if (!e) return;
  localStorage.setItem("pf_last_profile", JSON.stringify(e.profile));
  localStorage.setItem("pf_last_warnings", JSON.stringify(e.warnings));
  window.location.href = "/profile";
};

window.downloadEntry = function(id) {
  const h = getHistory();
  const e = h.find(x => x.id === id);
  if (!e) return;
  const blob = new Blob([JSON.stringify(e.profile, null, 2)], { type:"application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${e.name.replace(/\s+/g, "_")}_profile.json`;
  a.click();
  URL.revokeObjectURL(a.href);
};

window.deleteEntry = function(id) {
  if (!confirm("Delete this profile entry?")) return;
  const h = getHistory().filter(x => x.id !== id);
  saveHistory(h);
  render();
};

document.getElementById("clear-all-btn")?.addEventListener("click", () => {
  if (!confirm("Clear all profile history? This cannot be undone.")) return;
  saveHistory([]);
  render();
});

searchInput.addEventListener("input", render);
sortSel.addEventListener("change", render);
statusSel.addEventListener("change", render);

render();
