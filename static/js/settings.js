/**
 * Minimal Settings System
 * Handles theme persistence and smooth transitions
 * Production-ready with zero dependencies
 */

const Settings = (function () {
    "use strict";

    const STORAGE_KEY = "sc_theme";
    const THEME_DARK = "dark";
    const THEME_LIGHT = "light";

    let currentTheme = THEME_DARK;

    function init() {
        loadTheme();
        applyTheme(currentTheme);
        setupThemeToggle();
        setupTransitions();
    }

    function loadTheme() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored && [THEME_DARK, THEME_LIGHT].includes(stored)) {
                currentTheme = stored;
            }
        } catch (e) {
            currentTheme = THEME_DARK;
        }
    }

    function applyTheme(theme) {
        const t = [THEME_DARK, THEME_LIGHT].includes(theme) ? theme : THEME_DARK;
        document.documentElement.setAttribute("data-theme", t);
        document.body.setAttribute("data-theme", t);
        currentTheme = t;
        try { localStorage.setItem(STORAGE_KEY, t); } catch (e) {}
        window.dispatchEvent(new CustomEvent("themeChanged", { detail: { theme: t } }));
    }

    function getTheme() { return currentTheme; }

    function toggleTheme() {
        applyTheme(currentTheme === THEME_DARK ? THEME_LIGHT : THEME_DARK);
    }

    function setupThemeToggle() {
        const btn = document.getElementById("theme-toggle");
        if (!btn) return;
        btn.addEventListener("click", () => {
            toggleTheme();
        });
    }

    function setupTransitions() {
        const style = document.createElement("style");
        style.textContent = "html.prevent-transitions,html.prevent-transitions *{transition:none!important}";
        document.head.appendChild(style);
        document.documentElement.classList.add("prevent-transitions");
        requestAnimationFrame(() => document.documentElement.classList.remove("prevent-transitions"));
    }

    return { init, toggleTheme, getTheme, applyTheme, THEME_DARK, THEME_LIGHT };
})();

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => Settings.init());
} else {
    Settings.init();
}
