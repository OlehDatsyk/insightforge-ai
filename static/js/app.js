/**
 * app.js
 * ======
 * Shared shell behaviour: theme toggle (persisted in-memory + a cookie so
 * it survives reloads without using localStorage), mobile nav toggle,
 * active-link highlighting, and a small toast notification helper used by
 * every page.
 */
(function () {
  const THEME_COOKIE = "insightforge_theme";

  function readCookie(name) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }
  function writeCookie(name, value) {
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000`;
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    writeCookie(THEME_COOKIE, theme);
  }

  function initTheme() {
    const saved = readCookie(THEME_COOKIE);
    const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
    applyTheme(saved || (prefersLight ? "light" : "dark"));

    const toggle = document.getElementById("theme-toggle");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme");
        applyTheme(current === "dark" ? "light" : "dark");
      });
    }
  }

  function initNav() {
    const nav = document.getElementById("main-nav");
    const toggle = document.getElementById("nav-toggle");
    if (toggle && nav) {
      toggle.addEventListener("click", () => nav.classList.toggle("open"));
    }
    const path = window.location.pathname;
    document.querySelectorAll(".main-nav a").forEach((link) => {
      const href = link.getAttribute("href");
      if (href === "/" ? path === "/" : path.startsWith(href)) {
        link.classList.add("active");
      }
    });
  }

  window.showToast = function showToast(message, type = "info") {
    const stack = document.getElementById("toast-stack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity 200ms ease";
      setTimeout(() => el.remove(), 220);
    }, 4200);
  };

  window.escapeHtml = function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  };

  window.formatDate = function formatDate(iso) {
    if (!iso) return "-";
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_) {
      return iso;
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initNav();
  });
})();
