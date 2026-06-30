/* ============================================================
   ProfileForge — Frontend Application
   ============================================================ */

"use strict";

// ── State ──────────────────────────────────────────────────────
const state = {
  csvFile: null,
  pdfFile: null,
  lastResult: null,
};

// ── DOM refs ───────────────────────────────────────────────────
const form         = document.getElementById("upload-form");
const submitBtn    = document.getElementById("submit-btn");
const btnLabel     = submitBtn.querySelector(".btn__label");
const btnSpinner   = submitBtn.querySelector(".btn__spinner");

const csvInput     = document.getElementById("csv-input");
const pdfInput     = document.getElementById("pdf-input");
const csvZone      = document.getElementById("csv-zone");
const pdfZone      = document.getElementById("pdf-zone");
const csvChip      = document.getElementById("csv-chip");
const pdfChip      = document.getElementById("pdf-chip");
const csvName      = document.getElementById("csv-name");
const pdfName      = document.getElementById("pdf-name");
const configInput  = document.getElementById("config-input");

const errorBanner  = document.getElementById("error-banner");
const errorText    = document.getElementById("error-text");
const warnBanner   = document.getElementById("warn-banner");
const warnList     = document.getElementById("warn-list");

const uploadSection  = document.getElementById("upload-section");
const resultsSection = document.getElementById("results-section");
const resultsSub     = document.getElementById("results-subtitle");
const overviewEl     = document.getElementById("overview");
const fieldsGridEl   = document.getElementById("fields-grid");
const rawJsonEl      = document.getElementById("raw-json");

const copyBtn      = document.getElementById("copy-btn");
const downloadBtn  = document.getElementById("download-btn");
const resetBtn     = document.getElementById("reset-btn");

// ── Helpers ────────────────────────────────────────────────────
function setError(msg) {
  errorText.textContent = msg;
  errorBanner.hidden = false;
  errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function clearError() { errorBanner.hidden = true; }

function setLoading(yes) {
  submitBtn.disabled = yes;
  btnLabel.hidden = yes;
  btnSpinner.hidden = !yes;
}

function updateSubmitState() {
  submitBtn.disabled = !(state.csvFile && state.pdfFile);
}

function confColor(score) {
  if (score >= 0.8) return "#34d399";
  if (score >= 0.6) return "#fbbf24";
  return "#f87171";
}
function confBadgeClass(score) {
  if (score >= 0.8) return "conf-badge--high";
  if (score >= 0.6) return "conf-badge--medium";
  return "conf-badge--low";
}
function formatScore(score) { return Math.round(score * 100) + "%" }

function sourcePills(sources) {
  if (!sources || sources.length === 0) return "<span class='conf-label'>no source</span>";
  return sources.map(s => {
    const cls = s === "Resume" ? "pill--resume" : s === "CSV" ? "pill--csv" : "pill--other";
    return `<span class="pill ${cls}">${s}</span>`;
  }).join("");
}

// ── File selection ─────────────────────────────────────────────
function selectFile(type, file) {
  if (!file) return;
  if (type === "csv") {
    state.csvFile = file;
    csvName.textContent = file.name;
    csvChip.hidden = false;
    csvZone.hidden = true;
  } else {
    state.pdfFile = file;
    pdfName.textContent = file.name;
    pdfChip.hidden = false;
    pdfZone.hidden = true;
  }
  updateSubmitState();
}

function clearFile(type) {
  if (type === "csv") {
    state.csvFile = null;
    csvInput.value = "";
    csvChip.hidden = true;
    csvZone.hidden = false;
  } else {
    state.pdfFile = null;
    pdfInput.value = "";
    pdfChip.hidden = true;
    pdfZone.hidden = false;
  }
  updateSubmitState();
}

// Drop zone click → open file dialog
[csvZone, pdfZone].forEach(zone => {
  zone.addEventListener("click", () => {
    const targetId = zone.dataset.target;
    document.getElementById(targetId).click();
  });
});

// File input change
csvInput.addEventListener("change", e => selectFile("csv", e.target.files[0]));
pdfInput.addEventListener("change", e => selectFile("pdf", e.target.files[0]));

// Clear buttons
document.querySelectorAll("[data-clear]").forEach(btn => {
  btn.addEventListener("click", e => { e.stopPropagation(); clearFile(btn.dataset.clear); });
});

// Drag-and-drop
function setupDrop(zone, type) {
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) selectFile(type, file);
  });
}
setupDrop(csvZone, "csv");
setupDrop(pdfZone, "pdf");

// ── Form submit ────────────────────────────────────────────────
form.addEventListener("submit", async e => {
  e.preventDefault();
  clearError();
  setLoading(true);

  const fd = new FormData();
  fd.append("csv", state.csvFile);
  fd.append("resume", state.pdfFile);
  const cfgText = configInput.value.trim();
  if (cfgText) fd.append("config", cfgText);

  // Collect platform links
  const linkFields = [
    "link_linkedin", "link_github", "link_portfolio",
    "link_leetcode", "link_hackerrank", "link_stackoverflow",
    "link_twitter", "link_kaggle"
  ];
  const links = {};
  linkFields.forEach(name => {
    const el = document.querySelector(`[name="${name}"]`);
    const val = el ? el.value.trim() : "";
    if (val) links[name.replace("link_", "")] = val;
  });
  if (Object.keys(links).length > 0) {
    fd.append("platform_links", JSON.stringify(links));
  }

  try {
    const res = await fetch("/api/process", { method: "POST", body: fd });
    const data = await res.json();

    if (!res.ok || !data.success) {
      setError(data.error || "An unknown error occurred.");
      setLoading(false);
      return;
    }

    state.lastResult = data;
    renderResults(data);

  } catch (err) {
    setError("Could not reach the server. Is ProfileForge running?");
  } finally {
    setLoading(false);
  }
});

// ── Render results ─────────────────────────────────────────────
function renderResults(data) {
  const { profile, warnings } = data;

  // Warnings
  if (warnings && warnings.length > 0) {
    warnList.innerHTML = warnings.map(w => `<li>${escHtml(w)}</li>`).join("");
    warnBanner.hidden = false;
  } else {
    warnBanner.hidden = true;
  }

  // Subtitle
  const name = getVal(profile, "name") || getVal(profile, "full_name");
  const id = profile.candidate_id || "";
  resultsSub.textContent = `ID: ${id}` + (name ? ` · ${name}` : "");

  // Overview tiles
  renderOverview(profile);

  // Field cards
  renderFieldCards(profile);

  // Raw JSON
  rawJsonEl.textContent = JSON.stringify(profile, null, 2);

  // Show / hide sections
  uploadSection.hidden = true;
  resultsSection.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function getVal(profile, key) {
  const f = profile[key];
  if (!f) return null;
  if (typeof f === "object" && "value" in f) return f.value;
  return f;
}

function renderOverview(profile) {
  overviewEl.innerHTML = "";

  const tiles = [
    { label: "Name",        key: "name",             fallback: "full_name" },
    { label: "Location",    key: "location",          isLocation: true },
    { label: "Experience",  key: "years_experience",  suffix: " yrs" },
    { label: "Skills",      key: "skills",            isCount: true, unit: "skills" },
    { label: "Emails",      key: "emails",            isCount: true, unit: "emails" },
    { label: "Phones",      key: "phones",            isCount: true, unit: "phones" },
  ];

  tiles.forEach(t => {
    let fv = profile[t.key] || (t.fallback && profile[t.fallback]);
    if (!fv) return;

    let displayVal = "";
    if (t.isLocation) {
      const loc = fv.value || {};
      displayVal = [loc.city, loc.region, loc.country].filter(Boolean).join(", ") || "—";
    } else if (t.isCount) {
      const arr = fv.value || [];
      displayVal = arr.length + " " + t.unit;
    } else {
      const v = fv.value;
      displayVal = (v !== null && v !== undefined) ? String(v) + (t.suffix || "") : "—";
    }

    const conf = fv.confidence || 0;
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.innerHTML = `
      <div class="tile__label">${t.label}</div>
      <div class="tile__value ${displayVal === "—" ? "tile__value--muted" : ""}">${escHtml(displayVal)}</div>
      <div class="tile__conf">
        <div class="conf-bar">
          <div class="conf-bar__fill" style="width:${conf * 100}%;background:${confColor(conf)}"></div>
        </div>
        <span class="conf-label">Confidence: ${formatScore(conf)}</span>
      </div>
    `;
    overviewEl.appendChild(tile);
  });
}

function renderFieldCards(profile) {
  fieldsGridEl.innerHTML = "";

  // Fields to show as cards (skip candidate_id and overview fields)
  const CARD_FIELDS = [
    "full_name", "name", "headline", "emails", "phones",
    "skills", "location", "links", "experience",
  ];

  const allKeys = Object.keys(profile).filter(k => k !== "candidate_id");

  allKeys.forEach(key => {
    const fv = profile[key];
    if (!fv || typeof fv !== "object" || !("value" in fv)) return;

    const card = document.createElement("div");
    card.className = "field-card";

    const conf = fv.confidence || 0;

    card.innerHTML = `
      <div class="field-card__name">
        <span>${key.replace(/_/g, " ")}</span>
        <span class="conf-badge ${confBadgeClass(conf)}">${formatScore(conf)}</span>
      </div>
      <div class="field-card__value">${renderValue(key, fv.value)}</div>
      <div class="field-card__meta">
        <div class="source-pills">${sourcePills(fv.sources)}</div>
      </div>
    `;
    fieldsGridEl.appendChild(card);
  });
}

function renderValue(key, value) {
  if (value === null || value === undefined) {
    return "<span class='field-card__value--null'>not found</span>";
  }

  // Arrays of strings → tags
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === "string") {
    return `<div class="tags">${value.map(v => `<span class="tag">${escHtml(v)}</span>`).join("")}</div>`;
  }

  // Skills / emails / phones empty array
  if (Array.isArray(value) && value.length === 0) {
    return "<span class='field-card__value--null'>none</span>";
  }

  // Experience entries
  if (key === "experience" && Array.isArray(value)) {
    if (value.length === 0) return "<span class='field-card__value--null'>none</span>";
    return `<div class="exp-list">${value.map(e => `
      <div class="exp-entry">
        <div class="exp-entry__title">${escHtml(e.title || "Unknown role")}</div>
        <div class="exp-entry__company">${escHtml(e.company || "")}</div>
        <div class="exp-entry__dates">${escHtml(e.start_date || "")} – ${escHtml(e.end_date || "")}</div>
      </div>
    `).join("")}</div>`;
  }

  // Location object
  if (key === "location" && typeof value === "object") {
    return `<div class="nested-obj">
      ${value.city    ? `<div><span class="nested-key">City: </span>${escHtml(value.city)}</div>` : ""}
      ${value.region  ? `<div><span class="nested-key">Region: </span>${escHtml(value.region)}</div>` : ""}
      ${value.country ? `<div><span class="nested-key">Country: </span>${escHtml(value.country)}</div>` : ""}
    </div>`;
  }

  // Links object
  if (key === "links" && typeof value === "object") {
    const entries = Object.entries(value)
      .filter(([, v]) => v && (typeof v === "string" ? v.trim() : v.length > 0));
    if (entries.length === 0) return "<span class='field-card__value--null'>none</span>";
    return `<div class="nested-obj">${entries.map(([k, v]) =>
      `<div><span class="nested-key">${k}: </span>${Array.isArray(v) ? v.join(", ") : escHtml(String(v))}</div>`
    ).join("")}</div>`;
  }

  // Generic fallback
  return escHtml(String(value));
}

function escHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Action buttons ─────────────────────────────────────────────
copyBtn.addEventListener("click", async () => {
  if (!state.lastResult) return;
  await navigator.clipboard.writeText(JSON.stringify(state.lastResult.profile, null, 2));
  copyBtn.textContent = "Copied!";
  setTimeout(() => (copyBtn.textContent = "Copy JSON"), 2000);
});

downloadBtn.addEventListener("click", () => {
  if (!state.lastResult) return;
  const blob = new Blob(
    [JSON.stringify(state.lastResult.profile, null, 2)],
    { type: "application/json" }
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "candidate_profile.json";
  a.click();
  URL.revokeObjectURL(url);
});

resetBtn.addEventListener("click", () => {
  // Reset form state
  clearFile("csv");
  clearFile("pdf");
  configInput.value = "";
  clearError();
  warnBanner.hidden = true;
  state.lastResult = null;
  overviewEl.innerHTML = "";
  fieldsGridEl.innerHTML = "";
  rawJsonEl.textContent = "";

  uploadSection.hidden = false;
  resultsSection.hidden = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
});
