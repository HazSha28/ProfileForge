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
  const linksHtml = Object.entries(linksVal)
    .filter(([,v]) => v && (typeof v === "string" ? v : v.length))
    .map(([k,v]) => `<div style="font-size:.82rem;margin-bottom:4px;"><span style="color:var(--dim);font-size:.75rem;">${k}: </span><a href="${esc(v)}" target="_blank" style="color:var(--brown-l);">${esc(Array.isArray(v)?v.join(", "):v)}</a></div>`)
    .join("");
  document.getElementById("links-card").innerHTML = `
    <div class="pf-field-card__header"><span class="pf-field-card__name">Links</span></div>
    <div class="pf-field-card__value">${linksHtml || '<span style="color:var(--dim);font-style:italic">None</span>'}</div>
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
`;
document.head.appendChild(style);
