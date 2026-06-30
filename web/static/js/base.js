"use strict";

const sidebar       = document.getElementById("sidebar");
const collapseBtn   = document.getElementById("sidebar-collapse");
const mobileToggle  = document.getElementById("sidebar-mobile-toggle");

// ── Collapsible sidebar ────────────────────────────────────────
const COLLAPSED_KEY = "pf_sidebar_collapsed";

function applyCollapsed(collapsed) {
  if (collapsed) {
    sidebar?.classList.add("collapsed");
  } else {
    sidebar?.classList.remove("collapsed");
  }
}

// Restore saved state
applyCollapsed(localStorage.getItem(COLLAPSED_KEY) === "1");

collapseBtn?.addEventListener("click", () => {
  const isNowCollapsed = !sidebar.classList.contains("collapsed");
  applyCollapsed(isNowCollapsed);
  localStorage.setItem(COLLAPSED_KEY, isNowCollapsed ? "1" : "0");
});

// ── Mobile sidebar toggle ──────────────────────────────────────
mobileToggle?.addEventListener("click", () => {
  if (sidebar) {
    const hidden = sidebar.style.display === "none" || getComputedStyle(sidebar).display === "none";
    sidebar.style.display = hidden ? "flex" : "none";
  }
});
