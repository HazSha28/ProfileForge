"use strict";

const profile  = JSON.parse(localStorage.getItem("pf_last_profile") || "null");
const warnings = JSON.parse(localStorage.getItem("pf_last_warnings") || "[]");

if (!profile) {
  document.getElementById("no-profile").hidden = false;
  document.getElementById("profile-content").hidden = true;
} else {
  renderProfile(profile, warnings);
}

function gv(field) {
  // Get value from a FieldValue object or plain value
  if (!field) return null;
  if (typeof field === "object" && "value" in field) return field.value;
  return field;
}

function gc(field) { return (field && field.confidence) ? field.confidence : 0; }
function gs(field) { return (field && field.sources) ? field.sources : []; }

function confColor(c) {
  if (c >= 0.8) return "#3a7d52";
  if (c >= 0.6) return "#b07d20";
  return "#963030";
}

function sourcePills(sources) {
  return (sources || []).map(s => {
    const cls = s === "Resume" ? "pf-source-pill--resume" : "pf-source-pill--csv";
    return `<span class="pf-source-pill ${cls}">${s}</span>`;
  }).join("");
}

function confBar(score) {
  return `
    <div class="pf-conf">
      <div class="pf-conf__bar">
        <div class="pf-conf__fill" style="width:${score*100}%;background:${confColor(score)}"></div>
      </div>
      <span class="pf-conf__label">${Math.round(score*100)}%</span>
    </div>`;
}

function esc(s) {
  if (!s && s !== 0) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function renderProfile(p, warns) {
  // Warnings
  if (warns.length) {
    document.getElementById("warn-list").innerHTML = warns.map(w => `<li>${esc(w)}</li>`).join("");
    document.getElementById("warn-banner").hidden = false;
  }

  // Hero
  const name = gv(p.name) || gv(p.full_name) || "Unknown Candidate";
  document.getElementById("profile-name").textContent = name;
  document.getElementById("profile-name-crumb").textContent = name.split(" ")[0];
  document.getElementById("profile-avatar").textContent = name.charAt(0).toUpperCase();
  document.getElementById("profile-headline").textContent = gv(p.headline) || "Candidate";
  document.getElementById("profile-id").textContent = "ID: " + (p.candidate_id || "—");

  const loc = gv(p.location) || {};
  const locStr = [loc.city, loc.region, loc.country].filter(Boolean).join(", ");
  document.getElementById("profile-location").querySelector("span").textContent = locStr || "—";

  const yrs = gv(p.years_experience);
  document.getElementById("profile-exp").querySelector("span").textContent =
    yrs ? `${yrs} years experience` : "";

  // Skills
  const skills = gv(p.skills) || [];
  document.getElementById("skills-tags").innerHTML =
    skills.length ? skills.map(s => `<span class="pf-tag">${esc(s)}</span>`).join("") : "<span style='color:var(--dim);font-size:.82rem;'>No skills found</span>";
  const sc = gc(p.skills);
  document.getElementById("skills-conf-fill").style.width = `${sc*100}%`;
  document.getElementById("skills-conf-fill").style.background = confColor(sc);
  document.getElementById("skills-conf-label").textContent = `${Math.round(sc*100)}% confidence`;
  document.getElementById("skills-conf-badge").textContent = `${skills.length} skills`;
  document.getElementById("skills-sources").innerHTML = sourcePills(gs(p.skills));

  // Experience timeline
  const exp = gv(p.experience) || [];
  const tl = document.getElementById("experience-timeline");
  if (exp.length) {
    tl.innerHTML = exp.map(e => `
      <div class="pf-timeline-entry">
        <div class="pf-timeline-dot"></div>
        <div>
          <div class="pf-timeline-entry__title">${esc(e.title || "Unknown Role")}</div>
          <div class="pf-timeline-entry__company">${esc(e.company || "")}</div>
          <div class="pf-timeline-entry__dates">${esc(e.start_date || "")} ${e.end_date ? "– " + esc(e.end_date) : ""}</div>
        </div>
      </div>`).join("");
  } else {
    tl.innerHTML = "<span style='color:var(--dim);font-size:.82rem;'>No experience entries found</span>";
  }

  // Emails card
  renderListCard("emails-card", "Emails", gv(p.emails), gc(p.emails), gs(p.emails));

  // Phones card
  renderListCard("phones-card", "Phones", gv(p.phones), gc(p.phones), gs(p.phones));

  // Location card
  const locCard = document.getElementById("location-card");
  locCard.innerHTML = `
    <div class="pf-field-card__header">
      <span class="pf-field-card__name">Location</span>
    </div>
    <div class="pf-field-card__value">${locStr || '<span style="color:var(--dim);font-style:italic">Not found</span>'}</div>
    <div class="pf-field-card__footer">${confBar(gc(p.location))}<div class="pf-sources">${sourcePills(gs(p.location))}</div></div>`;

  // Links card
  const linksVal = gv(p.links) || {};

  function renderLinkItem(key, val) {
    if (!val) return "";
    // Handle arrays (e.g. "other" links)
    if (Array.isArray(val)) {
      return val.filter(Boolean).map((url, i) => {
        const label = key === "other" ? (i === 0 ? "Portfolio" : `Other ${i}`) : key;
        return renderSingleLink(label, url);
      }).join("");
    }
    return renderSingleLink(key, val);
  }

  function renderSingleLink(label, url) {
    if (!url || typeof url !== "string") return "";
    // Ensure URL has protocol
    const href = url.startsWith("http") ? url : "https://" + url;
    // Display label: capitalise and make readable
    const displayLabel = label.charAt(0).toUpperCase() + label.slice(1);
    // Short display text: just the domain/path without protocol
    const displayUrl = url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
    return `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="color:var(--dim);font-size:.74rem;min-width:70px">${esc(displayLabel)}:</span>
        <a href="${href}" target="_blank" rel="noopener noreferrer"
           style="color:var(--brown-l);font-size:.82rem;font-weight:600;text-decoration:none;
                  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;
                  transition:color .15s;"
           onmouseover="this.style.textDecoration='underline'"
           onmouseout="this.style.textDecoration='none'"
           title="${href}">${esc(displayUrl)}</a>
        <a href="${href}" target="_blank" rel="noopener noreferrer"
           style="color:var(--dim);flex-shrink:0;" title="Open ${displayLabel}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </a>
      </div>`;
  }

  const linkOrder = ["linkedin", "github", "portfolio", "other"];
  const linksHtml = linkOrder
    .map(k => renderLinkItem(k, linksVal[k]))
    .join("") ||
    '<span style="color:var(--dim);font-style:italic;font-size:.82rem">None</span>';

  document.getElementById("links-card").innerHTML = `
    <div class="pf-field-card__header"><span class="pf-field-card__name">Links</span></div>
    <div class="pf-field-card__value" style="padding-top:4px">${linksHtml}</div>
    <div class="pf-field-card__footer">${confBar(gc(p.links))}<div class="pf-sources">${sourcePills(gs(p.links))}</div></div>`;

  // Confidence overview
  const confFields = ["full_name","name","emails","phones","skills","location","years_experience"];
  const confList = document.getElementById("confidence-list");
  confFields.forEach(key => {
    const fv = p[key];
    if (!fv || typeof fv !== "object" || !("confidence" in fv)) return;
    const c = fv.confidence;
    const row = document.createElement("div");
    row.style.cssText = "display:flex;align-items:center;gap:10px;";
    row.innerHTML = `
      <span style="font-size:.78rem;color:var(--muted);width:110px;flex-shrink:0;text-transform:capitalize;">${key.replace(/_/g," ")}</span>
      <div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden;">
        <div style="height:100%;border-radius:3px;background:${confColor(c)};width:${c*100}%;transition:width .5s"></div>
      </div>
      <span style="font-size:.72rem;color:var(--dim);width:32px;text-align:right;">${Math.round(c*100)}%</span>`;
    confList.appendChild(row);
  });

  // Raw JSON
  document.getElementById("raw-json").textContent = JSON.stringify(p, null, 2);

  // View tabs
  document.querySelectorAll(".pf-view-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pf-view-tab").forEach(b => b.classList.remove("pf-view-tab--active"));
      btn.classList.add("pf-view-tab--active");
      const view = btn.dataset.view;
      document.getElementById("view-formatted").hidden = view !== "formatted";
      document.getElementById("view-json").hidden = view !== "json";
    });
  });

  // Copy / Download
  [document.getElementById("copy-btn"), document.getElementById("copy-btn-2")].forEach(btn => {
    if (!btn) return;
    btn.addEventListener("click", async () => {
      await navigator.clipboard.writeText(JSON.stringify(p, null, 2));
      const orig = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => btn.textContent = orig, 2000);
    });
  });

  document.getElementById("download-btn").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(p, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "candidate_profile.json";
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

function renderListCard(id, label, values, conf, sources) {
  const el = document.getElementById(id);
  const items = Array.isArray(values) ? values : (values ? [values] : []);
  el.innerHTML = `
    <div class="pf-field-card__header"><span class="pf-field-card__name">${label}</span></div>
    <div class="pf-field-card__value">
      ${items.length ? items.map(v => `<div>${esc(v)}</div>`).join("") : '<span style="color:var(--dim);font-style:italic">None</span>'}
    </div>
    <div class="pf-field-card__footer">${confBar(conf)}<div class="pf-sources">${sourcePills(sources)}</div></div>`;
}

// Add view tab CSS inline
const style = document.createElement("style");
style.textContent = `
.pf-view-tab {
  padding:7px 16px; border:1px solid var(--border); background:transparent;
  border-radius:var(--radius-sm); font-size:.82rem; font-weight:600;
  color:var(--muted); cursor:pointer; transition:.15s;
}
.pf-view-tab:hover { border-color:var(--border-2); color:var(--text-2); }
.pf-view-tab--active { background:var(--brown); border-color:var(--brown); color:#f2e8d9; }

/* ── Edit mode ── */
.pf-editable {
  border: 1px dashed transparent;
  border-radius: 5px;
  transition: border-color .15s, background .15s;
  min-height: 1.2em;
  display: inline-block;
  padding: 2px 4px;
  cursor: default;
}
body.edit-mode .pf-editable {
  border-color: var(--brown-l);
  background: var(--brown-glow);
  cursor: text;
  outline: none;
}
body.edit-mode .pf-editable:focus {
  border-color: var(--brown);
  background: var(--surface-2);
  box-shadow: 0 0 0 3px rgba(107,63,31,.12);
}
.pf-manual-badge {
  display: inline-block; font-size: .6rem; font-weight: 800;
  padding: 1px 6px; border-radius: 10px; margin-left: 5px;
  background: rgba(91,74,138,.15); color: var(--purple);
  border: 1px solid rgba(91,74,138,.25); text-transform: uppercase;
  letter-spacing: .4px; vertical-align: middle;
}
.pf-edit-hint {
  font-size: .72rem; color: var(--brown-l);
  margin-bottom: 14px; padding: 8px 12px;
  background: rgba(107,63,31,.07); border-radius: 7px;
  border: 1px solid rgba(107,63,31,.15);
  display: none;
}
body.edit-mode .pf-edit-hint { display: block; }
`;
document.head.appendChild(style);

// ── Edit mode ──────────────────────────────────────────────────
let editMode = false;
let originalProfile = JSON.parse(JSON.stringify(p || {})); // deep clone for cancel

const editBtn       = document.getElementById("edit-btn");
const saveBtn       = document.getElementById("save-edit-btn");
const cancelBtn     = document.getElementById("cancel-edit-btn");

// Insert edit hint banner at top of formatted view
const editHint = document.createElement("div");
editHint.className = "pf-edit-hint";
editHint.innerHTML = `
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13" style="display:inline;vertical-align:middle;margin-right:5px">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
  </svg>
  <strong>Edit mode</strong> — click any field to correct it. Changes are tracked as <span class="pf-manual-badge">Manual</span> source.
`;
document.getElementById("view-formatted")?.prepend(editHint);

function makeEditable(el, fieldKey, subKey) {
  if (!el) return;
  el.classList.add("pf-editable");
  el.setAttribute("data-field", fieldKey);
  if (subKey) el.setAttribute("data-subkey", subKey);
}

function enterEditMode() {
  editMode = true;
  originalProfile = JSON.parse(JSON.stringify(p));
  document.body.classList.add("edit-mode");

  // Make all editable fields contenteditable
  document.querySelectorAll(".pf-editable").forEach(el => {
    el.contentEditable = "true";
    el.setAttribute("spellcheck", "false");
  });

  editBtn.hidden    = true;
  saveBtn.hidden    = false;
  cancelBtn.hidden  = false;
}

function exitEditMode(save) {
  editMode = false;
  document.body.classList.remove("edit-mode");

  document.querySelectorAll(".pf-editable").forEach(el => {
    el.contentEditable = "false";
  });

  if (save) {
    applyEdits();
    // Persist updated profile to localStorage
    localStorage.setItem("pf_last_profile", JSON.stringify(p));
    // Update history entry if it exists
    updateHistoryEntry(p);
    showSavedToast();
  } else {
    // Restore original — re-render
    Object.assign(p, originalProfile);
    renderProfile(p, warnings);
  }

  editBtn.hidden    = false;
  saveBtn.hidden    = true;
  cancelBtn.hidden  = true;
}

function applyEdits() {
  document.querySelectorAll(".pf-editable").forEach(el => {
    const fieldKey = el.getAttribute("data-field");
    const subKey   = el.getAttribute("data-subkey");
    const newVal   = el.textContent.trim();

    if (!fieldKey || !p[fieldKey]) return;

    const fv = p[fieldKey];
    if (subKey) {
      // Nested field (e.g. location.city)
      if (fv.value && typeof fv.value === "object") {
        fv.value[subKey] = newVal;
      }
    } else {
      fv.value = newVal;
    }

    // Mark as manually edited
    if (!fv.sources.includes("Manual")) {
      fv.sources = [...fv.sources, "Manual"];
    }
    fv.confidence = 1.0;   // recruiter confirmed = full confidence

    // Add visual badge
    const existing = el.parentElement.querySelector(".pf-manual-badge");
    if (!existing) {
      const badge = document.createElement("span");
      badge.className = "pf-manual-badge";
      badge.textContent = "Manual";
      el.insertAdjacentElement("afterend", badge);
    }
  });
}

function updateHistoryEntry(updatedProfile) {
  try {
    const history = JSON.parse(localStorage.getItem("pf_history") || "[]");
    const idx = history.findIndex(e => e.id === updatedProfile.candidate_id);
    if (idx !== -1) {
      history[idx].profile = updatedProfile;
      history[idx].status  = "manual";
      localStorage.setItem("pf_history", JSON.stringify(history));
    }
  } catch(e) {}
}

function showSavedToast() {
  const toast = document.createElement("div");
  toast.style.cssText = `
    position:fixed; bottom:24px; right:24px; z-index:9999;
    background:var(--green); color:#fff; padding:10px 18px;
    border-radius:9px; font-size:.84rem; font-weight:600;
    box-shadow:0 4px 16px rgba(0,0,0,.2);
    animation: fadeUp .3s ease;
  `;
  toast.textContent = "✓ Changes saved";
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

editBtn?.addEventListener("click",   () => enterEditMode());
saveBtn?.addEventListener("click",   () => exitEditMode(true));
cancelBtn?.addEventListener("click", () => exitEditMode(false));

// Make key fields editable after render
requestAnimationFrame(() => {
  makeEditable(document.getElementById("profile-name"),     "full_name");
  makeEditable(document.getElementById("profile-headline"), "headline");
  // Location subfields — attempt to find them
  const locVal = document.querySelector("#location-card .pf-field-card__value");
  if (locVal) {
    locVal.classList.add("pf-editable");
    locVal.setAttribute("data-field", "location");
  }
});
