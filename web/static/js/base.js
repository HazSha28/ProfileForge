"use strict";

// Mobile sidebar toggle
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebar = document.getElementById("sidebar");
if (sidebarToggle && sidebar) {
  sidebarToggle.addEventListener("click", () => {
    sidebar.style.display = sidebar.style.display === "none" ? "flex" : "none";
  });
}
