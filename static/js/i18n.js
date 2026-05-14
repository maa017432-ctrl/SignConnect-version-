/**
 * i18n module for SignConnect — English / US ASL only.
 * Retained for backward-compatibility with code that calls i18n.t() / i18n.translate().
 */

const i18n = (function () {
    "use strict";

    const STORAGE_KEY = "signconnect_lang";

    // Always English
    localStorage.setItem(STORAGE_KEY, "en");

    function t(key, defaultValue) {
        return defaultValue !== undefined ? defaultValue : key;
    }

    function translate(key, defaultValue) {
        return t(key, defaultValue);
    }

    function getLanguage() { return "en"; }

    function getAvailableLanguages() {
        return [{ code: "en", name: "🇺🇸 English / US ASL" }];
    }

    function applyTranslations() {}

    function init() {
        document.documentElement.setAttribute("dir", "ltr");
    }

    return { init, t, translate, getLanguage, getAvailableLanguages, applyTranslations, STORAGE_KEY };
})();

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => i18n.init());
} else {
    i18n.init();
}
