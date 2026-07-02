"use strict";
// bulk.js — upload form for /bulk page

// ── Drop-zone helpers ──────────────────────────────────────────
function initDropZone(zoneId, inputId, chipId, nameId, clearKey) {
  const zone  = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const chip  = document.getElementById(chipId);
  const nameEl = document.getElementById(nameId);
  if (!zone || !input) return;

  zone.addEventListener("click", () => input.click());

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) setFile(input, file, chip, nameEl, zone);
  });

  input.addEventListener("change", () => {
    if (input.files[0]) setFile(input, input.files[0], chip, nameEl, zone);
  });

  // Clear button — use event delegation to avoid timing issues
  document.addEventListener("click", e => {
    const btn = e.target.closest(`[data-clear="${clearKey}"]`);
    if (!btn) return;
    e.stopPropagation();
    e.preventDefault();
    input.value = "";
    chip.hidden = true;
    zone.hidden = false;
    checkReady();
  });
}

function setFile(input, file, chip, nameEl, zone) {
  nameEl.textContent = file.name;
  chip.hidden = false;
  zone.hidden = true;
  checkReady();
}

// ── Template CSV download ──────────────────────────────────────
document.getElementById("download-template")?.addEventListener("click", () => {
  const csv = [
    "full_name,email,phone,city,country,skills,years_experience,linkedin",
    "Jane Doe,jane@example.com,+14155550101,San Francisco,US,\"Python,SQL,React\",4,https://linkedin.com/in/janedoe",
    "John Smith,john@example.com,+14155550102,New York,US,\"Java,Spring,Docker\",6,",
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = "recruiter_template.csv"; a.click();
  URL.revokeObjectURL(a.href);
});

// ── Submit readiness check ─────────────────────────────────────
const csvInput  = document.getElementById("csv-input");
const zipInput  = document.getElementById("zip-input");
const submitBtn = document.getElementById("submit-btn");

function checkReady() {
  const ready = csvInput?.files?.length > 0 && zipInput?.files?.length > 0;
  if (submitBtn) submitBtn.disabled = !ready;
}

// ── Form submit ────────────────────────────────────────────────
const form     = document.getElementById("bulk-form");
const btnLabel  = document.getElementById("btn-label");
const btnSpinner = document.getElementById("btn-spinner");

function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function showError(msg) {
  document.getElementById("pf-bulk-error-toast")?.remove();
  const toast = document.createElement("div");
  toast.id = "pf-bulk-error-toast";
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
      <div style="font-size:.85rem;font-weight:700;color:#fca5a5;margin-bottom:3px">Error</div>
      <div style="font-size:.8rem;color:#f87171;line-height:1.5">${esc(msg)}</div>
    </div>
    <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:#6b2020;font-size:1.1rem;line-height:1;padding:0 0 0 4px;flex-shrink:0">✕</button>
  `;
  if (!document.getElementById("pf-toast-style")) {
    const s = document.createElement("style");
    s.id = "pf-toast-style";
    s.textContent = `@keyframes slideUp{from{opacity:0;transform:translateX(-50%) translateY(12px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}`;
    document.head.appendChild(s);
  }
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 8000);
}

if (form) {
  form.addEventListener("submit", async e => {
    e.preventDefault();

    const csvFile = csvInput?.files?.[0];
    const zipFile = zipInput?.files?.[0];

    if (!csvFile || !zipFile) {
      showError("Please upload both the recruiter CSV and the resume ZIP.");
      return;
    }

    // Validate file types
    if (!csvFile.name.endsWith(".csv")) {
      showError("First file must be a .csv file."); return;
    }
    if (!zipFile.name.endsWith(".zip")) {
      showError("Second file must be a .zip archive."); return;
    }

    // Store files in sessionStorage reference (can't store binary, use IndexedDB-free approach)
    // We'll use a FormData POST to the SSE endpoint and redirect to progress page
    btnLabel.hidden  = true;
    btnSpinner.hidden = false;
    submitBtn.disabled = true;

    // Store files for bulk_progress.js to pick up
    // We use a hidden form technique — post to progress page which reads SSE
    const fd = new FormData();
    fd.append("csv", csvFile);
    fd.append("zip", zipFile);

    // Store FormData content in window.bulkFormData and navigate
    // Since we can't pass binary between pages, we use a different approach:
    // POST directly and redirect with job_id in the URL
    try {
      // We POST to the SSE endpoint and handle the stream on the progress page.
      // Store file refs in sessionStorage metadata, then navigate.
      const csvMeta = { name: csvFile.name, size: csvFile.size };
      const zipMeta = { name: zipFile.name, size: zipFile.size };
      sessionStorage.setItem("pf_bulk_csv_meta", JSON.stringify(csvMeta));
      sessionStorage.setItem("pf_bulk_zip_meta", JSON.stringify(zipMeta));

      // Read files as base64 and store (for small payloads; large files handled via streaming)
      const [csvB64, zipB64] = await Promise.all([
        fileToBase64(csvFile),
        fileToBase64(zipFile),
      ]);
      sessionStorage.setItem("pf_bulk_csv_b64", csvB64);
      sessionStorage.setItem("pf_bulk_zip_b64", zipB64);

      window.location.href = "/bulk/progress";
    } catch (err) {
      showError(`Failed to prepare upload: ${err.message}`);
      btnLabel.hidden  = false;
      btnSpinner.hidden = true;
      submitBtn.disabled = false;
    }
  });
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// Init drop zones
initDropZone("csv-zone", "csv-input", "csv-chip", "csv-name", "csv");
initDropZone("zip-zone", "zip-input", "zip-chip", "zip-name", "zip");
