"use strict";

// ── State ──────────────────────────────────────────────────────
const state = { csvFile: null, pdfFile: null };

// ── DOM refs ───────────────────────────────────────────────────
const form         = document.getElementById("upload-form");
const submitBtn    = document.getElementById("submit-btn");
const btnLabel     = document.getElementById("btn-label");
const btnSpinner   = document.getElementById("btn-spinner");
const errorBanner  = document.getElementById("error-banner");
const errorText    = document.getElementById("error-text");
const uploadView   = document.getElementById("upload-view");
const pipelineView = document.getElementById("pipeline-view");
const stagesEl     = document.getElementById("pipeline-stages");
const currentStep  = document.getElementById("pipeline-current-step");

// ── File selection ─────────────────────────────────────────────
function selectFile(type, file) {
  if (!file) return;
  if (type === "csv") {
    state.csvFile = file;
    document.getElementById("csv-name").textContent = file.name;
    document.getElementById("csv-chip").hidden = false;
    document.getElementById("csv-zone").hidden = true;
  } else {
    state.pdfFile = file;
    document.getElementById("pdf-name").textContent = file.name;
    document.getElementById("pdf-chip").hidden = false;
    document.getElementById("pdf-zone").hidden = true;
  }
  submitBtn.disabled = !(state.csvFile && state.pdfFile);
}

function clearFile(type) {
  if (type === "csv") {
    state.csvFile = null;
    document.getElementById("csv-input").value = "";
    document.getElementById("csv-chip").hidden = true;
    document.getElementById("csv-zone").hidden = false;
  } else {
    state.pdfFile = null;
    document.getElementById("pdf-input").value = "";
    document.getElementById("pdf-chip").hidden = true;
    document.getElementById("pdf-zone").hidden = false;
  }
  submitBtn.disabled = !(state.csvFile && state.pdfFile);
}

// ── Drop zones ─────────────────────────────────────────────────
["csv-zone", "pdf-zone"].forEach(zoneId => {
  const zone = document.getElementById(zoneId);
  const type = zoneId.startsWith("csv") ? "csv" : "pdf";
  const inputId = type === "csv" ? "csv-input" : "pdf-input";
  zone.addEventListener("click", () => document.getElementById(inputId).click());
  zone.addEventListener("dragover",  e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files[0]) selectFile(type, e.dataTransfer.files[0]);
  });
});

document.getElementById("csv-input").addEventListener("change", e => selectFile("csv", e.target.files[0]));
document.getElementById("pdf-input").addEventListener("change", e => selectFile("pdf", e.target.files[0]));

// Use event delegation on document for clear buttons — works even when chip is hidden/shown dynamically
document.addEventListener("click", e => {
  const btn = e.target.closest("[data-clear]");
  if (!btn) return;
  e.stopPropagation();
  e.preventDefault();
  clearFile(btn.dataset.clear);
});

// ── Pipeline stage UI ──────────────────────────────────────────
function addStage(text, status) {
  const existing = stagesEl.querySelector(`[data-step="${CSS.escape(text)}"]`);
  if (existing) { existing.className = `pf-stage pf-stage--${status}`; return; }
  const li = document.createElement("li");
  li.className = `pf-stage pf-stage--${status}`;
  li.dataset.step = text;
  li.innerHTML = `<div class="pf-stage__dot"></div><span>${text}</span>`;
  stagesEl.appendChild(li);
}

// ── Form submit — SSE stream on same page ──────────────────────
form.addEventListener("submit", async e => {
  e.preventDefault();
  errorBanner.hidden = true;

  // Build FormData
  const fd = new FormData();
  fd.append("csv",    state.csvFile);
  fd.append("resume", state.pdfFile);

  const config = document.getElementById("config-input")?.value?.trim();
  if (config) fd.append("config", config);

  const linkNames = ["link_linkedin","link_github","link_portfolio",
                     "link_leetcode","link_hackerrank","link_kaggle"];
  const links = {};
  linkNames.forEach(name => {
    const val = document.querySelector(`[name="${name}"]`)?.value?.trim();
    if (val) links[name.replace("link_", "")] = val;
  });
  if (Object.keys(links).length) fd.append("platform_links", JSON.stringify(links));

  // Switch to pipeline view
  uploadView.hidden   = true;
  pipelineView.hidden = false;
  stagesEl.innerHTML  = "";
  currentStep.textContent = "Starting pipeline...";

  try {
    const response = await fetch("/api/process/stream", { method: "POST", body: fd });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: "Unknown error" }));
      showError(err.error || err.detail || "Processing failed.");
      return;
    }

    // Read the SSE stream
    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        if (!block.trim()) continue;

        let eventType = "", dataStr = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) eventType = line.slice(7).trim();
          if (line.startsWith("data: "))  dataStr   = line.slice(6).trim();
        }
        if (!dataStr) continue;

        let data;
        try { data = JSON.parse(dataStr); }
        catch { continue; }

        if (eventType === "stage") {
          currentStep.textContent = data.step + (data.status === "running" ? "..." : " ✓");
          addStage(data.step, data.status);

        } else if (eventType === "error") {
          showError(data.message);
          return;

        } else if (eventType === "complete") {
          addStage("Profile Generated", "done");
          currentStep.textContent = "Done!";

          // Save to localStorage and redirect to profile page
          const runs = parseInt(localStorage.getItem("pf_runs") || "0") + 1;
          localStorage.setItem("pf_runs", runs);
          localStorage.setItem("pf_last_profile",  JSON.stringify(data.profile));
          localStorage.setItem("pf_last_warnings", JSON.stringify(data.warnings || []));
          // Save to history module
          if (window.pfSaveHistory) pfSaveHistory(data.profile, data.warnings);
          else {
            // inline save in case history.js not loaded
            try {
              const h = JSON.parse(localStorage.getItem("pf_history")||"[]");
              const name = data.profile?.name?.value || data.profile?.full_name?.value || "Unknown";
              h.unshift({ id: data.profile.candidate_id||Date.now().toString(), name, date:new Date().toISOString(),
                confidence:0.75, status:(data.warnings?.length?"warn":"ok"), warnings:data.warnings||[], profile:data.profile });
              if(h.length>100) h.splice(100);
              localStorage.setItem("pf_history", JSON.stringify(h));
            } catch(e){}
          }
          setTimeout(() => { window.location.href = "/profile"; }, 900);
        }
      }
    }

  } catch (err) {
    showError("Could not reach the server. Is ProfileForge running?");
  }
});

// ── Error helper — floating toast popup ───────────────────────
function showError(msg) {
  pipelineView.hidden = true;
  uploadView.hidden   = false;

  // Remove any existing toast
  document.getElementById("pf-error-toast")?.remove();

  const toast = document.createElement("div");
  toast.id = "pf-error-toast";
  toast.style.cssText = `
    position:fixed; bottom:28px; left:50%; transform:translateX(-50%);
    z-index:9999; min-width:320px; max-width:520px;
    background:#2a0f0f; border:1px solid rgba(150,48,48,.5);
    border-radius:10px; padding:14px 18px;
    display:flex; align-items:flex-start; gap:12px;
    box-shadow:0 8px 32px rgba(0,0,0,.4);
    animation:slideUp .25s ease;
  `;
  toast.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2" width="18" height="18" style="flex-shrink:0;margin-top:1px">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
      <circle cx="12" cy="16" r=".5" fill="#f87171" stroke="#f87171"/>
    </svg>
    <div style="flex:1">
      <div style="font-size:.85rem;font-weight:700;color:#fca5a5;margin-bottom:3px">Processing Error</div>
      <div style="font-size:.8rem;color:#f87171;line-height:1.5">${esc(msg)}</div>
    </div>
    <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:#6b2020;font-size:1.1rem;line-height:1;padding:0 0 0 4px;flex-shrink:0">✕</button>
  `;

  // Add slide-up animation
  if (!document.getElementById("pf-toast-style")) {
    const s = document.createElement("style");
    s.id = "pf-toast-style";
    s.textContent = `@keyframes slideUp { from{opacity:0;transform:translateX(-50%) translateY(12px)} to{opacity:1;transform:translateX(-50%) translateY(0)} }`;
    document.head.appendChild(s);
  }

  document.body.appendChild(toast);
  // Auto-dismiss after 8 seconds
  setTimeout(() => toast.remove(), 8000);
  errorBanner.hidden = true;   // keep static banner hidden
}

function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
