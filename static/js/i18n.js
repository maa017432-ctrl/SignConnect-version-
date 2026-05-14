/**
 * Internationalization (i18n) module for SignConnect
 * Handles language switching, translation loading, and RTL/LTR layout
 */

const i18n = (function () {
    "use strict";

    let currentLang = localStorage.getItem("signconnect_lang") || "en";
    let translations = {};
    const STORAGE_KEY = "signconnect_lang";
    const RTL_LANGUAGES = ["ar", "he", "ur"];

    /**
     * Load translations for a specific language
     */
    async function loadLanguage(lang) {
        try {
            const response = await fetch(`/api/translations/${lang}`);
            if (!response.ok) {
                console.error(`Failed to load translations for ${lang}`);
                lang = "en";
                const fallbackResponse = await fetch(`/api/translations/${lang}`);
                const data = await fallbackResponse.json();
                translations = data.translations || {};
            } else {
                const data = await response.json();
                translations = data.translations || {};
            }
            currentLang = lang;
            localStorage.setItem(STORAGE_KEY, lang);
            applyLayoutDirection();
            applyTranslations();
        } catch (error) {
            console.error("Error loading translations:", error);
        }
    }

    /**
     * Apply RTL or LTR layout based on language
     */
    function applyLayoutDirection() {
        const html = document.documentElement;
        if (RTL_LANGUAGES.includes(currentLang)) {
            html.setAttribute("dir", "rtl");
            document.body.style.direction = "rtl";
        } else {
            html.setAttribute("dir", "ltr");
            document.body.style.direction = "ltr";
        }
    }

    /**
     * Get a translation by key path (e.g., "nav.home")
     */
    function t(key, defaultValue = key) {
        const keys = key.split(".");
        let value = translations;

        for (const k of keys) {
            if (value && typeof value === "object" && k in value) {
                value = value[k];
            } else {
                return defaultValue;
            }
        }

        return typeof value === "string" ? value : defaultValue;
    }

    /**
     * Apply translations to all elements with data-i18n attribute
     */
    function applyTranslations() {
        // Elements with data-i18n attribute
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

        // Elements with data-i18n-placeholder attribute
        document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
            const key = element.getAttribute("data-i18n-placeholder");
            element.placeholder = t(key);
        });

        // Elements with data-i18n-title attribute
        document.querySelectorAll("[data-i18n-title]").forEach((element) => {
            const key = element.getAttribute("data-i18n-title");
            element.title = t(key);
        });
    }

    /**
     * Set the current language and update the UI
     */
    async function setLanguage(lang) {
        if (lang !== currentLang) {
            await loadLanguage(lang);
            window.dispatchEvent(new CustomEvent("languageChanged", { detail: { lang } }));
        }
    }

    /**
     * Get the current language
     */
    function getLanguage() {
        return currentLang;
    }

    /**
     * Get all available languages
     */
    function getAvailableLanguages() {
        return [
            { code: "en", name: "🇺🇸 English" },
            { code: "ar", name: "🇸🇦 العربية" },
            { code: "fr", name: "🇫🇷 Français" },
            { code: "es", name: "🇪🇸 Español" },
            { code: "de", name: "🇩🇪 Deutsch" },
            { code: "zh", name: "🇨🇳 中文" },
            { code: "ja", name: "🇯🇵 日本語" },
            { code: "ko", name: "🇰🇷 한국어" }
        ];
    }

    /**
     * Initialize i18n system
     */
    async function init() {
        await loadLanguage(currentLang);
        setupLanguageSwitchers();
    }

    /**
     * Setup language switcher event listeners
     */
    function setupLanguageSwitchers() {
        const langSelects = document.querySelectorAll("[data-lang-select]");
        langSelects.forEach((select) => {
            select.addEventListener("change", (event) => {
                setLanguage(event.target.value);
            });
            // Set current language in select
            select.value = currentLang;
        });
    }

    /**
     * Translate a key and return the value
     * (public alias for t())
     */
    function translate(key, defaultValue = key) {
        return t(key, defaultValue);
    }

    return {
        init,
        t,
        translate,
        setLanguage,
        getLanguage,
        getAvailableLanguages,
        applyTranslations,
        STORAGE_KEY
    };
})();

// Initialize i18n when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => i18n.init());
} else {
    i18n.init();
}
