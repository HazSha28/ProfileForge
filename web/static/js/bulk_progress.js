"use strict";
// bulk_progress.js — real-time SSE progress renderer for /bulk/progress

// ── State ──────────────────────────────────────────────────────
let totalCandidates  = 0;
let doneCandidates   = 0;
let failedCandidates = 0;
let missingCandidates = 0;
let confidenceScores = [];
let jobStartTime     = Date.now();
let jobId            = null;
const candidates     = {};   // index → row data
const allResults     = [];   // for bulk_history save

// ── DOM refs ───────────────────────────────────────────────────
const statusText   = document.getElementById("bp-status-text");
const barFill      = document.getElementById("bp-bar-fill");
const pct          = document.getElementById("bp-pct");
const stageLabel   = document.getElementById("bp-stage-label");
const doneCount    = document.getElementById("bp-done-count");
const totalCount   = document.getElementById("bp-total-count");
const tbody        = document.getElementById("bp-tbody");
const currentName  = document.getElementById("bp-current-name");
const currentResume = document.getElementById("bp-current-resume");
const currentBadge = document.getElementById("bp-current-badge");
const etaEl        = document.getElementById("bp-eta");
const logEl        = document.getElementById("bp-log");
const completeBanner = document.getElementById("bp-complete-banner");
const completeTitle  = document.getElementById("bp-complete-title");
const completeSub    = document.getElementById("bp-complete-sub");
const statProcessed  = document.getElementById("bps-processed");
const statFailed     = document.getElementById("bps-failed");
const statMissing    = document.getElementById("bps-missing");
const statConf       = document.getElementById("bps-confidence");

// ── Progress helpers ───────────────────────────────────────────
function setProgress(n, total) {
  const p = total > 0 ? Math.round((n / total) * 100) : 0;
  if (barFill)    barFill.style.width  = p + "%";
  if (pct)        pct.textContent      = p + "%";
  if (doneCount)  doneCount.textContent = n;
  if (totalCount) totalCount.textContent = total;
}

function updateStats() {
  if (statProcessed) statProcessed.textContent = doneCandidates;
  if (statFailed)    statFailed.textContent     = failedCandidates;
  if (statMissing)   statMissing.textContent    = missingCandidates;
  if (statConf) {
    const avg = confidenceScores.length
      ? confidenceScores.reduce((a, b) => a + b, 0) / confidenceScores.length
      : 0;
    statConf.textContent = confidenceScores.length
      ? Math.round(avg * 100) + "%" : "—";
  }
}

function confColor(c) {
  if (c >= 0.8) return "#3a7d52";
  if (c >= 0.6) return "#b07d20";
  return "#963030";
}

function badgeHTML(status) {
  const map = {
    processing:     ["bp-badge--processing", "Processing…"],
    done:           ["bp-badge--done",    "✓ Done"],
    failed:         ["bp-badge--failed",  "✗ Failed"],
    resume_missing: ["bp-badge--missing", "⚠ No Resume"],
    csv_missing:    ["bp-badge--missing", "⚠ No CSV Row"],
    pending:        ["bp-badge--pending", "Pending"],
  };
  const [cls, label] = map[status] || ["bp-badge--pending", status];
  return `<span class="bp-badge ${cls}">${label}</span>`;
}

function matchBadge(method) {
  const map = {
    email:      "#5a90c8", phone: "#b07d20",
    exact_name: "#3a7d52", fuzzy_name: "#6b3f1f", none: "#7a8fa8",
  };
  const col = map[method] || "#7a8fa8";
  return `<span style="font-size:.68rem;color:${col};font-weight:700;">${method || "—"}</span>`;
}

function upsertRow(c) {
  const id = `bp-row-${c.index}`;
  let tr = document.getElementById(id);
  if (!tr) {
    tr = document.createElement("tr");
    tr.id = id;
    tbody?.appendChild(tr);
  }

  const confVal  = c.confidence || 0;
  const confPct  = Math.round(confVal * 100);
  const confCol  = confColor(confVal);

  tr.innerHTML = `
    <td style="width:36px;color:var(--dim);font-size:.76rem;padding:10px 8px">${c.index}</td>
    <td style="padding:10px 12px;max-width:160px">
      <div style="font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(c.name)}">${esc(c.name)}</div>
      <div style="font-size:.72rem;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(c.email || "")}</div>
    </td>
    <td style="padding:10px 8px;width:140px;max-width:140px;font-size:.73rem;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(c.resume_name || "")}">${esc(c.resume_name || "—")}</td>
    <td style="padding:10px 8px;width:80px;white-space:nowrap">${matchBadge(c.match_method)}</td>
    <td style="padding:10px 8px;width:110px">${badgeHTML(c.status)}</td>
    <td style="padding:10px 8px;width:120px">
      ${confPct > 0 ? `
        <div style="display:flex;align-items:center;gap:6px">
          <div style="width:52px;min-width:52px;height:4px;background:var(--border);border-radius:2px;overflow:hidden;flex-shrink:0">
            <div style="width:${confPct}%;height:100%;background:${confCol};border-radius:2px"></div>
          </div>
          <span style="font-size:.76rem;color:var(--muted);white-space:nowrap">${confPct}%</span>
        </div>` : '<span style="color:var(--dim);font-size:.76rem">—</span>'}
    </td>
  `;
}

function logEntry(msg, type = "") {
  if (!logEl) return;
  const now = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const div = document.createElement("div");
  div.className = `bp-log-entry${type ? " bp-log-entry--" + type : ""}`;
  div.innerHTML = `<span class="bp-log-entry__time">${now}</span> ${esc(msg)}`;
  logEl.prepend(div);
  // Keep last 50 entries
  while (logEl.children.length > 50) logEl.removeChild(logEl.lastChild);
}

function estimateETA() {
  if (!totalCandidates || !doneCandidates) return;
  const elapsed = (Date.now() - jobStartTime) / 1000;
  const rate    = doneCandidates / elapsed;
  const remaining = totalCandidates - doneCandidates;
  if (rate > 0 && remaining > 0) {
    const secs = Math.round(remaining / rate);
    if (etaEl) etaEl.textContent = `ETA: ~${secs}s · ${remaining} remaining`;
  }
}

// ── SSE event handlers ─────────────────────────────────────────
function handleEvent(event) {
  const data = JSON.parse(event.data);
  jobId = data.job_id;

  switch (data.type) {

    case "job_start":
      totalCandidates = data.total;
      jobStartTime    = Date.now();
      if (statusText)  statusText.textContent = data.message || "Processing…";
      if (stageLabel)  stageLabel.textContent = `Processing ${data.total} candidates…`;
      setProgress(0, data.total);
      logEntry(`Job ${data.job_id} started — ${data.total} candidates`, "");
      break;

    case "candidate_start": {
      const c = data.candidate;
      candidates[c.index] = c;
      upsertRow(c);
      if (currentName)   currentName.textContent   = c.name || "—";
      if (currentResume) currentResume.textContent = c.resume_name ? `📄 ${c.resume_name}` : "";
      if (currentBadge)  currentBadge.hidden = false;
      if (statusText)    statusText.textContent = `Processing ${c.name}…`;
      estimateETA();
      break;
    }

    case "candidate_done": {
      const c = data.candidate;
      candidates[c.index] = c;
      allResults.push(c);
      upsertRow(c);

      if (c.status === "done") {
        doneCandidates++;
        if (c.confidence) confidenceScores.push(c.confidence);
        logEntry(`✓ ${c.name} — ${Math.round((c.confidence||0)*100)}% confidence`, "done");
      } else if (c.status === "resume_missing") {
        missingCandidates++;
        logEntry(`⚠ ${c.name} — resume missing`, "warn");
      } else {
        doneCandidates++;
      }

      setProgress(data.current, totalCandidates);
      updateStats();
      estimateETA();
      break;
    }

    case "candidate_error": {
      const c = data.candidate;
      candidates[c.index] = c;
      upsertRow(c);
      failedCandidates++;
      setProgress(data.current, totalCandidates);
      updateStats();
      logEntry(`✗ ${c.name} — ${c.error || "pipeline error"}`, "failed");
      break;
    }

    case "job_complete": {
      const s = data.summary;
      if (statusText)  statusText.textContent = "Complete";
      if (stageLabel)  stageLabel.textContent = "All candidates processed";
      if (currentBadge) currentBadge.hidden = true;
      if (currentName)  currentName.textContent = "Done";
      if (etaEl)        etaEl.textContent = `Completed in ${s?.processing_time || "—"}`;
      setProgress(totalCandidates, totalCandidates);

      // Show complete banner
      if (completeBanner) completeBanner.hidden = false;
      if (completeTitle)  completeTitle.textContent =
        `Bulk processing complete — ${s?.processed || 0}/${s?.total_candidates || 0} processed`;
      if (completeSub) completeSub.textContent =
        `${s?.failed || 0} failed · ${s?.resume_missing || 0} resume missing · `+
        `avg confidence ${Math.round((s?.average_confidence||0)*100)}% · ${s?.processing_time}`;

      logEntry(`Job ${data.job_id} complete`, "done");

      // Save to bulk history in localStorage
      _saveBulkHistory(data.job_id, allResults, s);
      break;
    }

    case "job_error":
      if (statusText) statusText.textContent = `Error: ${data.message}`;
      logEntry(`Job error: ${data.message}`, "failed");
      break;
  }
}

// ── localStorage — bulk history ────────────────────────────────
function _saveBulkHistory(jobId, candidates, summary) {
  try {
    const history = JSON.parse(localStorage.getItem("pf_bulk_history") || "[]");
    history.unshift({
      job_id:    jobId,
      date:      new Date().toISOString(),
      summary,
      candidates,
    });
    // Keep last 20 bulk jobs
    if (history.length > 20) history.splice(20);
    localStorage.setItem("pf_bulk_history", JSON.stringify(history));
    // Also push each candidate into single-profile history
    _pushToSingleHistory(candidates);
  } catch (e) {
    console.error("Failed to save bulk history:", e);
  }
}

function _pushToSingleHistory(candidates) {
  try {
    const h = JSON.parse(localStorage.getItem("pf_history") || "[]");
    for (const c of candidates) {
      if (!c.profile) continue;
      h.unshift({
        id:         c.profile.candidate_id || crypto.randomUUID(),
        name:       c.name,
        date:       c.processed_at || new Date().toISOString(),
        confidence: c.confidence || 0,
        status:     c.warnings?.length ? "warn" : "ok",
        warnings:   c.warnings || [],
        profile:    c.profile,
        source:     "bulk",
      });
    }
    if (h.length > 200) h.splice(200);
    localStorage.setItem("pf_history", JSON.stringify(h));
  } catch (e) {
    console.error("Failed to push to profile history:", e);
  }
}

// ── Start SSE stream from stored files ────────────────────────
async function startProcessing() {
  const csvB64 = sessionStorage.getItem("pf_bulk_csv_b64");
  const zipB64 = sessionStorage.getItem("pf_bulk_zip_b64");
  const csvMeta = JSON.parse(sessionStorage.getItem("pf_bulk_csv_meta") || "null");
  const zipMeta = JSON.parse(sessionStorage.getItem("pf_bulk_zip_meta") || "null");

  if (!csvB64 || !zipB64) {
    if (statusText) statusText.textContent = "No upload data found — please go back and upload files.";
    logEntry("No file data found in session. Redirecting…", "failed");
    setTimeout(() => window.location.href = "/bulk", 2000);
    return;
  }

  if (statusText) statusText.textContent = "Uploading files…";
  if (stageLabel) stageLabel.textContent = "Preparing upload…";

  // Convert base64 back to Blob
  const csvBlob = b64ToBlob(csvB64, "text/csv");
  const zipBlob = b64ToBlob(zipB64, "application/zip");

  const fd = new FormData();
  fd.append("csv", csvBlob, csvMeta?.name || "recruiter.csv");
  fd.append("zip", zipBlob, zipMeta?.name || "resumes.zip");

  // Clear session storage
  sessionStorage.removeItem("pf_bulk_csv_b64");
  sessionStorage.removeItem("pf_bulk_zip_b64");

  // POST to SSE endpoint using fetch + ReadableStream
  try {
    const resp = await fetch("/api/bulk/process/stream", {
      method: "POST",
      body:   fd,
    });

    if (!resp.ok) {
      const err = await resp.text();
      if (statusText) statusText.textContent = `Upload failed: ${resp.status}`;
      logEntry(`HTTP ${resp.status}: ${err}`, "failed");
      return;
    }

    if (stageLabel) stageLabel.textContent = "Processing…";

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // Parse SSE chunks
      const lines = buf.split("\n\n");
      buf = lines.pop() || "";  // keep incomplete last chunk

      for (const chunk of lines) {
        for (const line of chunk.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              const event = { data: line.slice(6) };
              handleEvent(event);
            } catch (e) {
              console.error("SSE parse error:", e);
            }
          }
        }
      }
    }
  } catch (err) {
    if (statusText) statusText.textContent = `Connection error: ${err.message}`;
    logEntry(`Connection error: ${err.message}`, "failed");
  }
}

function b64ToBlob(b64, mime) {
  const bytes = atob(b64);
  const arr   = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

function esc(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── Boot ───────────────────────────────────────────────────────
startProcessing();
