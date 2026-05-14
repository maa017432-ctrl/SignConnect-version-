/**
 * Lightweight i18n module constrained to English + US ASL labels.
 */
const i18n = (function () {
    "use strict";

    const STORAGE_KEY = "signconnect_lang";
    const SUPPORTED_LANGS = ["en", "asl"];
    let currentLang = SUPPORTED_LANGS.includes(localStorage.getItem(STORAGE_KEY))
        ? localStorage.getItem(STORAGE_KEY)
        : "en";
    let translations = {};

    function normalizeLang(lang) {
        return SUPPORTED_LANGS.includes(lang) ? lang : "en";
    }

    async function loadLanguage(lang) {
        const normalized = normalizeLang(String(lang || "").trim().toLowerCase());
        try {
            const response = await fetch(`/api/translations/${normalized}`);
            if (!response.ok) {
                throw new Error(`Failed to load translations for ${normalized}`);
            }
            const data = await response.json();
            translations = data.translations || {};
            currentLang = normalizeLang(data.lang || normalized);
            localStorage.setItem(STORAGE_KEY, currentLang);
            document.documentElement.setAttribute("dir", "ltr");
            applyTranslations();
        } catch (error) {
            console.error("Error loading translations:", error);
        }
    }

    function t(key, defaultValue = key) {
        const keys = key.split(".");
        let value = translations;
        for (const k of keys) {
            if (value && typeof value === "object" && k in value) value = value[k];
            else return defaultValue;
        }
        return typeof value === "string" ? value : defaultValue;
    }

    function applyTranslations() {
        document.querySelectorAll("[data-i18n]").forEach((element) => {
            const key = element.getAttribute("data-i18n");
            const text = t(key);
            if (element.tagName === "INPUT" && (element.type === "button" || element.type === "submit")) {
                element.value = text;
            } else if (element.tagName === "IMG") {
                element.alt = text;
            } else {
                element.textContent = text;
            }
        });

        document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
            const key = element.getAttribute("data-i18n-placeholder");
            element.placeholder = t(key);
        });

        document.querySelectorAll("[data-i18n-title]").forEach((element) => {
            const key = element.getAttribute("data-i18n-title");
            element.title = t(key);
        });
    }

    async function setLanguage(lang) {
        const normalized = normalizeLang(String(lang || "").trim().toLowerCase());
        if (normalized !== currentLang) {
            await loadLanguage(normalized);
            window.dispatchEvent(new CustomEvent("languageChanged", { detail: { lang: normalized } }));
        }
    }

    function getLanguage() {
        return currentLang;
    }

    function getAvailableLanguages() {
        return [
            { code: "en", name: "English" },
            { code: "asl", name: "US ASL" },
        ];
    }

    async function init() {
        await loadLanguage(currentLang);
        const langSelects = document.querySelectorAll("[data-lang-select]");
        langSelects.forEach((select) => {
            select.value = currentLang;
            select.addEventListener("change", (event) => setLanguage(event.target.value));
        });
    }

    return {
        init,
        t,
        translate: t,
        setLanguage,
        getLanguage,
        getAvailableLanguages,
        applyTranslations,
        STORAGE_KEY,
    };
})();

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => i18n.init());
} else {
    i18n.init();
}
