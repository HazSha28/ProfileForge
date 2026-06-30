"use strict";
const sections = document.querySelectorAll(".legal-section[id]");
const navLinks  = document.querySelectorAll(".legal-nav__link");
function onScroll() {
  let current = "";
  sections.forEach(sec => {
    if (sec.getBoundingClientRect().top <= 100) current = sec.id;
  });
  navLinks.forEach(link => {
    const href = link.getAttribute("href").replace("#", "");
    link.classList.toggle("legal-nav__link--active", href === current);
  });
}
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();
