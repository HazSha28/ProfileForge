"use strict";

const sidebar   = document.getElementById("sidebar");
const toggle    = document.getElementById("sidebar-toggle");
const overlay   = document.getElementById("sidebar-overlay");

const COLLAPSED_KEY = "pf_sidebar_collapsed";
const MOBILE_BP     = 700; // matches CSS breakpoint

// ── Helpers ────────────────────────────────────────────────────
function isMobile() {
  return window.innerWidth <= MOBILE_BP;
}

function setCollapsed(collapsed) {
  if (!sidebar) return;
  sidebar.classList.toggle("collapsed", collapsed);

  // On desktop, persist preference
  if (!isMobile()) {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }
}

function setMobileOpen(open) {
  if (!sidebar) return;
  sidebar.classList.toggle("mobile-open", open);
  if (overlay) overlay.classList.toggle("active", open);
  document.body.classList.toggle("sidebar-overlay-active", open);
}

// ── Init ───────────────────────────────────────────────────────
(function init() {
  if (isMobile()) {
    // Mobile: always start closed
    setMobileOpen(false);
  } else {
    // Desktop: restore saved collapsed state
    const saved = localStorage.getItem(COLLAPSED_KEY) === "1";
    setCollapsed(saved);
  }
})();

// ── Toggle button click ────────────────────────────────────────
toggle?.addEventListener("click", () => {
  if (isMobile()) {
    const isOpen = sidebar.classList.contains("mobile-open");
    setMobileOpen(!isOpen);
  } else {
    const isCollapsed = sidebar.classList.contains("collapsed");
    setCollapsed(!isCollapsed);
  }
});

// ── Overlay click — close mobile sidebar ──────────────────────
overlay?.addEventListener("click", () => {
  setMobileOpen(false);
});

// ── Resize — switch between mobile / desktop modes ────────────
window.addEventListener("resize", () => {
  if (isMobile()) {
    // entering mobile: remove desktop collapsed, ensure overlay cleared
    sidebar?.classList.remove("collapsed");
    setMobileOpen(false);
  } else {
    // leaving mobile: remove mobile-open, restore desktop state
    sidebar?.classList.remove("mobile-open");
    if (overlay) overlay.classList.remove("active");
    document.body.classList.remove("sidebar-overlay-active");
    const saved = localStorage.getItem(COLLAPSED_KEY) === "1";
    setCollapsed(saved);
  }
});
