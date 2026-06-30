"use strict";

// Highlight active sidebar link based on scroll position
const sections = document.querySelectorAll(".help-section[id]");
const navLinks  = document.querySelectorAll(".help-nav__link");

function onScroll() {
  let current = "";
  sections.forEach(sec => {
    const top = sec.getBoundingClientRect().top;
    if (top <= 100) current = sec.id;
  });
  navLinks.forEach(link => {
    const href = link.getAttribute("href").replace("#", "");
    link.classList.toggle("help-nav__link--active", href === current);
  });
}

window.addEventListener("scroll", onScroll, { passive: true });
onScroll();
