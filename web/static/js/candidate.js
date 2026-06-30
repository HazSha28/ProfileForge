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
document.querySelectorAll("[data-clear]").forEach(btn =>
  btn.addEventListener("click", e => { e.stopPropagation(); clearFile(btn.dataset.clear); })
);

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

// ── Error helper ───────────────────────────────────────────────
function showError(msg) {
  pipelineView.hidden = true;
  uploadView.hidden   = false;
  errorText.textContent = msg;
  errorBanner.hidden    = false;
  errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
