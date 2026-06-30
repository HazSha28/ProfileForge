"use strict";

// ── Tab switching ──────────────────────────────────────────────
const tabSignin  = document.getElementById("tab-signin");
const tabSignup  = document.getElementById("tab-signup");
const panelSignin = document.getElementById("panel-signin");
const panelSignup = document.getElementById("panel-signup");

function activateTab(tab) {
  const isSignin = tab === "signin";
  tabSignin.classList.toggle("auth-tab--active", isSignin);
  tabSignup.classList.toggle("auth-tab--active", !isSignin);
  panelSignin.hidden = !isSignin;
  panelSignup.hidden = isSignin;
}

document.querySelectorAll(".auth-tab").forEach(btn => {
  btn.addEventListener("click", () => {
    activateTab(btn.dataset.panel === "panel-signin" ? "signin" : "signup");
  });
});

// ── Password visibility toggle ─────────────────────────────────
document.querySelectorAll(".auth-eye").forEach(btn => {
  btn.addEventListener("click", () => {
    const input = document.getElementById(btn.dataset.target);
    if (!input) return;
    input.type = input.type === "password" ? "text" : "password";
    // Swap icon opacity to hint state
    btn.style.opacity = input.type === "text" ? "0.5" : "1";
  });
});

// ── Password strength meter ────────────────────────────────────
const pwdInput  = document.getElementById("signup-password");
const pwdFill   = document.getElementById("pwd-fill");
const pwdLabel  = document.getElementById("pwd-label");

function scorePassword(pwd) {
  if (!pwd) return 0;
  let score = 0;
  if (pwd.length >= 8)  score++;
  if (pwd.length >= 12) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^A-Za-z0-9]/.test(pwd)) score++;
  return score;
}

const strengthMap = [
  { label: "",          color: "transparent",  width: "0%" },
  { label: "Weak",      color: "#963030",       width: "20%" },
  { label: "Fair",      color: "#b07d20",       width: "45%" },
  { label: "Good",      color: "#3a7d52",       width: "70%" },
  { label: "Strong",    color: "#2d6b44",       width: "85%" },
  { label: "Very strong", color: "#1e5c36",     width: "100%" },
];

if (pwdInput) {
  pwdInput.addEventListener("input", () => {
    const score = scorePassword(pwdInput.value);
    const s = strengthMap[score] || strengthMap[0];
    pwdFill.style.width = s.width;
    pwdFill.style.background = s.color;
    pwdLabel.textContent = s.label;
    pwdLabel.style.color = s.color;
  });
}

// ── Field validation helpers ───────────────────────────────────
function setError(inputId, errId, msg) {
  const input = document.getElementById(inputId);
  const err   = document.getElementById(errId);
  if (input) input.classList.toggle("is-error", !!msg);
  if (input) input.classList.toggle("is-valid", !msg && input.value.trim() !== "");
  if (err) err.textContent = msg || "";
}

function validateEmail(val) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(val);
}

// ── Sign In ────────────────────────────────────────────────────
const signinForm  = document.getElementById("signin-form");
const signinError = document.getElementById("signin-error");
const signinBtn   = document.getElementById("signin-btn");

if (signinForm) {
  signinForm.addEventListener("submit", async e => {
    e.preventDefault();
    let valid = true;

    const email = document.getElementById("signin-email").value.trim();
    const pass  = document.getElementById("signin-password").value;

    if (!email || !validateEmail(email)) {
      setError("signin-email", "signin-email-err", "Enter a valid email address.");
      valid = false;
    } else {
      setError("signin-email", "signin-email-err", "");
    }

    if (!pass) {
      setError("signin-password", "signin-pass-err", "Password is required.");
      valid = false;
    } else {
      setError("signin-password", "signin-pass-err", "");
    }

    if (!valid) return;

    // ── Loading state ──
    signinBtn.disabled = true;
    signinBtn.querySelector(".auth-btn__label").hidden = true;
    signinBtn.querySelector(".auth-btn__spinner").hidden = false;
    signinError.hidden = true;

    // Simulate auth (replace with real API call)
    await new Promise(r => setTimeout(r, 1200));

    // For demo: any credentials work and redirect to main app
    window.location.href = "/";
  });
}

// ── Sign Up ────────────────────────────────────────────────────
const signupForm    = document.getElementById("signup-form");
const signupError   = document.getElementById("signup-error");
const signupSuccess = document.getElementById("signup-success");
const signupBtn     = document.getElementById("signup-btn");

if (signupForm) {
  signupForm.addEventListener("submit", async e => {
    e.preventDefault();
    let valid = true;

    const first    = document.getElementById("signup-first").value.trim();
    const last     = document.getElementById("signup-last").value.trim();
    const email    = document.getElementById("signup-email").value.trim();
    const pass     = document.getElementById("signup-password").value;
    const confirm  = document.getElementById("signup-confirm").value;
    const agreed   = document.getElementById("agree-terms").checked;

    if (!first) {
      setError("signup-first", "signup-first-err", "First name is required.");
      valid = false;
    } else { setError("signup-first", "signup-first-err", ""); }

    if (!last) {
      setError("signup-last", "signup-last-err", "Last name is required.");
      valid = false;
    } else { setError("signup-last", "signup-last-err", ""); }

    if (!email || !validateEmail(email)) {
      setError("signup-email", "signup-email-err", "Enter a valid email address.");
      valid = false;
    } else { setError("signup-email", "signup-email-err", ""); }

    if (!pass || pass.length < 8) {
      setError("signup-password", "signup-pass-err", "Password must be at least 8 characters.");
      valid = false;
    } else { setError("signup-password", "signup-pass-err", ""); }

    if (pass !== confirm) {
      setError("signup-confirm", "signup-confirm-err", "Passwords do not match.");
      valid = false;
    } else { setError("signup-confirm", "signup-confirm-err", ""); }

    if (!agreed) {
      signupError.textContent = "You must agree to the Terms of Service to continue.";
      signupError.hidden = false;
      valid = false;
    } else {
      signupError.hidden = true;
    }

    if (!valid) return;

    // ── Loading state ──
    signupBtn.disabled = true;
    signupBtn.querySelector(".auth-btn__label").hidden = true;
    signupBtn.querySelector(".auth-btn__spinner").hidden = false;

    // Simulate registration (replace with real API call)
    await new Promise(r => setTimeout(r, 1400));

    signupBtn.disabled = false;
    signupBtn.querySelector(".auth-btn__label").hidden = false;
    signupBtn.querySelector(".auth-btn__spinner").hidden = true;

    // Show success and switch to sign-in tab
    signupSuccess.textContent = `Account created for ${first}! Please sign in.`;
    signupSuccess.hidden = false;

    setTimeout(() => {
      signupSuccess.hidden = true;
      activateTab("signin");
      document.getElementById("signin-email").value = email;
    }, 2000);
  });
}

// ── Social buttons — real OAuth redirects ─────────────────────
document.querySelectorAll(".auth-social-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const provider = btn.dataset.provider;
    if (provider === "google") {
      window.location.href = "/auth/google";
    } else if (provider === "github") {
      window.location.href = "/auth/github";
    }
  });
});
