# Language Support & Internationalization (i18n)

SignConnect now supports **8 languages** with full UI translation and automatic RTL (Right-to-Left) layout support for Arabic.

## Supported Languages

- 🇺🇸 **English** (en)
- 🇸🇦 **Arabic** (ar) - with RTL layout
- 🇫🇷 **French** (fr)
- 🇪🇸 **Spanish** (es)
- 🇩🇪 **German** (de)
- 🇨🇳 **Chinese Simplified** (zh)
- 🇯🇵 **Japanese** (ja)
- 🇰🇷 **Korean** (ko)

## Architecture

### Translation System Components

1. **Translation File** (`static/data/translations.json`)
   - JSON file containing all UI strings organized by language
   - Organized into logical sections: nav, settings, translator, home, dictionary, history, status

2. **i18n JavaScript Module** (`static/js/i18n.js`)
   - Handles loading translations from the API
   - Manages language switching
   - Applies translations to DOM elements via `data-i18n` attributes
   - Handles RTL/LTR layout switching automatically
   - Stores user's language preference in localStorage

3. **API Endpoint** (`/api/translations/<lang>`)
   - Serves translations for a specific language
   - Falls back to English if requested language is unavailable
   - Returns JSON with all translations for the selected language

4. **CSS RTL Support** (`static/css/design.css`)
   - RTL-aware CSS rules for Arabic and other RTL languages
   - Uses `html[dir="rtl"]` selector for language-specific styling
   - Automatically applied by the i18n module

## How It Works

### For Users

1. **Language Switching**
   - Users can switch languages via two select elements:
     - Main translator page: `#lang-select`
     - Settings modal: `#settings-lang-select`
   - Both selects are synchronized
   - Language preference is saved to localStorage

2. **Automatic RTL**
   - When switching to Arabic, the entire UI automatically switches to RTL
   - Navigation reverses direction
   - Text alignment adjusts automatically
   - Form elements and inputs adapt

3. **Persistent Selection**
   - User's language choice is saved in localStorage
   - Same language used on next visit
   - Settings and main page language select stay in sync

### For Developers

#### Adding New Language

1. **Add translations to `static/data/translations.json`:**
```json
{
  "xx": {
    "nav": {
      "home": "Your translation",
      ...
    },
    ...
  }
}
```

2. **Update the language list in `i18n.js`:**
```javascript
function getAvailableLanguages() {
  return [
    ...
    { code: "xx", name: "🏳️ Language Name" },
    ...
  ];
}
```

3. **Update HTML select options** (translator.html, base.html):
```html
<option value="xx">🏳️ Language Name</option>
```

#### Using i18n in Templates

**Basic text translation:**
```html
<h2 data-i18n="home.title">Translate Sign Language Into Text and Speech Instantly</h2>
```

**Placeholder translation:**
```html
<input 
  type="text" 
  data-i18n-placeholder="translator.search_gesture"
  placeholder="Search gesture..."
>
```

**Title attribute translation:**
```html
<button data-i18n-title="some.key" title="Button tooltip">Click me</button>
```

#### Using i18n in JavaScript

```javascript
// Get a translation
const text = i18n.t("home.title");

// Set language
i18n.setLanguage("ar");

// Get current language
const currentLang = i18n.getLanguage();

// Get available languages
const langs = i18n.getAvailableLanguages();

// Listen for language changes
window.addEventListener("languageChanged", (event) => {
  console.log("Language changed to:", event.detail.lang);
});
```

## File Structure

```
static/
├── data/
│   └── translations.json       # All translation strings
├── js/
│   ├── i18n.js                 # i18n module (new)
│   └── app.js                  # Updated with i18n integration
└── css/
    └── design.css              # Updated with RTL support

routes/
└── api.py                       # New endpoint: /api/translations/<lang>

templates/
├── base.html                   # Updated with i18n attributes
├── index.html                  # Updated with i18n attributes
├── translator.html             # Updated with i18n attributes
├── dictionary.html             # Updated with i18n attributes
└── history.html                # Updated with i18n attributes
```

## Usage Examples

### Switching Language via JavaScript

```javascript
// User clicks language select
i18n.setLanguage("ar");  // Switches to Arabic with RTL layout
```

### Adding New Translatable Text

1. Add to `static/data/translations.json`:
```json
{
  "en": {
    "mySection": {
      "myKey": "English text here"
    }
  },
  "ar": {
    "mySection": {
      "myKey": "النص العربي هنا"
    }
  }
}
```

2. Use in template:
```html
<p data-i18n="mySection.myKey">English text here</p>
```

3. Access in JavaScript:
```javascript
const text = i18n.t("mySection.myKey");
```

## Technical Details

### localStorage Keys

- `signconnect_lang` - Current selected language (set by i18n module)
- `sc_lang` - Current selected language (legacy, set by app.js for backward compatibility)

### API Response Format

```json
{
  "lang": "ar",
  "translations": {
    "nav": { "home": "الرئيسية", ... },
    "settings": { ... },
    ...
  }
}
```

### RTL Detection

Languages that trigger RTL layout automatically:
- `ar` (Arabic)
- `he` (Hebrew) - can be added in future
- `ur` (Urdu) - can be added in future

### Fallback Behavior

- If a language is not found → Falls back to English
- If a translation key is not found → Returns the key itself
- If `translations.json` fails to load → Uses cached translations

## Troubleshooting

### Language not changing?
- Check browser console for errors
- Verify language code is in the supported list
- Clear localStorage and refresh

### RTL layout broken?
- Ensure `html[dir="rtl"]` CSS rules are loaded
- Check browser dev tools for `dir` attribute on `<html>` element
- Verify text direction CSS is applied

### Missing translations?
- Check `static/data/translations.json` for the key
- Verify the key path is correct (e.g., "section.subsection.key")
- Check console for fallback warnings

## Future Enhancements

- [ ] Add more languages (Persian, Urdu, Hindi, etc.)
- [ ] Implement translation editing interface
- [ ] Add language auto-detection based on browser locale
- [ ] Create translation contribution workflow
- [ ] Add keyboard shortcut for language switching
- [ ] Implement language-specific date/number formatting
