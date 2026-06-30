"use strict";

// ── State ──────────────────────────────────────────────────────
const state = { csvFile: null, pdfFile: null };

// ── DOM ────────────────────────────────────────────────────────
const form       = document.getElementById("upload-form");
const submitBtn  = document.getElementById("submit-btn");
const btnLabel   = document.getElementById("btn-label");
const btnSpinner = document.getElementById("btn-spinner");
const errorBanner= document.getElementById("error-banner");
const errorText  = document.getElementById("error-text");
const uploadView = document.getElementById("upload-view");
const pipelineView = document.getElementById("pipeline-view");
const stagesEl   = document.getElementById("pipeline-stages");
const currentStep= document.getElementById("pipeline-current-step");

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

// Drop zones
["csv-zone", "pdf-zone"].forEach(zoneId => {
  const zone = document.getElementById(zoneId);
  const type = zoneId.startsWith("csv") ? "csv" : "pdf";
  zone.addEventListener("click", () => document.getElementById(type === "csv" ? "csv-input" : "pdf-input").click());
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("drag-over");
    if (e.dataTransfer.files[0]) selectFile(type, e.dataTransfer.files[0]);
  });
});

document.getElementById("csv-input").addEventListener("change", e => selectFile("csv", e.target.files[0]));
document.getElementById("pdf-input").addEventListener("change", e => selectFile("pdf", e.target.files[0]));
document.querySelectorAll("[data-clear]").forEach(btn =>
  btn.addEventListener("click", e => { e.stopPropagation(); clearFile(btn.dataset.clear); })
);

// ── Pipeline stage helpers ─────────────────────────────────────
function addStage(text, status = "running") {
  const li = document.createElement("li");
  li.className = `pf-stage pf-stage--${status}`;
  li.dataset.step = text;
  li.innerHTML = `<div class="pf-stage__dot"></div><span>${text}</span>`;
  stagesEl.appendChild(li);
  return li;
}

function updateStage(text, status) {
  const li = stagesEl.querySelector(`[data-step="${text}"]`);
  if (li) {
    li.className = `pf-stage pf-stage--${status}`;
  } else {
    addStage(text, status);
  }
}

// ── Form submit — SSE streaming ────────────────────────────────
form.addEventListener("submit", async e => {
  e.preventDefault();
  errorBanner.hidden = true;

  const fd = new FormData();
  fd.append("csv", state.csvFile);
  fd.append("resume", state.pdfFile);

  const config = document.getElementById("config-input")?.value?.trim();
  if (config) fd.append("config", config);

  // Collect platform links
  const linkNames = ["link_linkedin","link_github","link_portfolio","link_leetcode","link_hackerrank","link_kaggle"];
  const links = {};
  linkNames.forEach(name => {
    const el = document.querySelector(`[name="${name}"]`);
    const val = el?.value?.trim();
    if (val) links[name.replace("link_", "")] = val;
  });
  if (Object.keys(links).length) fd.append("platform_links", JSON.stringify(links));

  // Switch to pipeline view
  uploadView.hidden = true;
  pipelineView.hidden = false;
  stagesEl.innerHTML = "";

  try {
    const response = await fetch("/api/process/stream", { method: "POST", body: fd });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Unknown error" }));
      showError(err.detail || "Processing failed.");
      return;
    }

    // Read SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        if (!event.trim()) continue;
        const lines = event.split("\n");
        let eventType = "", dataStr = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) eventType = line.slice(7).trim();
          if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
        }
        if (!dataStr) continue;
        const data = JSON.parse(dataStr);

        if (eventType === "stage") {
          if (data.status === "running") {
            currentStep.textContent = data.step + "...";
            addStage(data.step, "running");
          } else if (data.status === "done") {
            updateStage(data.step, "done");
          }
        } else if (eventType === "error") {
          showError(data.message);
          return;
        } else if (eventType === "complete") {
          updateStage("Profile Generated", "done");
          currentStep.textContent = "Done!";
          // Increment run counter
          const runs = parseInt(localStorage.getItem("pf_runs") || "0") + 1;
          localStorage.setItem("pf_runs", runs);
          // Store profile and redirect
          localStorage.setItem("pf_last_profile", JSON.stringify(data.profile));
          localStorage.setItem("pf_last_warnings", JSON.stringify(data.warnings || []));
          setTimeout(() => { window.location.href = "/profile"; }, 800);
        }
      }
    }
  } catch (err) {
    showError("Could not connect to the server.");
  }
});

function showError(msg) {
  pipelineView.hidden = true;
  uploadView.hidden = false;
  errorText.textContent = msg;
  errorBanner.hidden = false;
  errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
