/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema de Internacionalización
 * Selector manual (ES/EN) + detección por país/IP + Preferencia en localStorage
 */

const LanguageSwitcher = (function () {
  const STORAGE_KEY = 'cds-language';
  const MANUAL_KEY = 'cds-language-manual';

  /** Idiomas visibles y seleccionables en el menú */
  const menuLanguages = ['es', 'en'];

  /** Idiomas con archivo en /locales (carga segura) */
  const availableLanguages = ['es', 'en', 'fr', 'zh', 'de', 'ar', 'ru'];

  /** Traducciones del idioma activo (objeto `translations` del JSON). */
  let currentTranslations = null;

  const languageNames = {
    es: 'Español',
    en: 'English',
    fr: 'Français',
    zh: '中文',
    de: 'Deutsch',
    ar: 'العربية',
    ru: 'Русский',
  };

  function getNested(obj, path) {
    if (!obj || !path) return undefined;
    return path.split('.').reduce((o, key) => (o && o[key] != null ? o[key] : undefined), obj);
  }

  function getTranslations() {
    return currentTranslations;
  }

  /** Resuelve una clave i18n (p. ej. `checkout.errors.name`). */
  function t(path) {
    const value = getNested(currentTranslations, path);
    return typeof value === 'string' ? value : value != null ? value : undefined;
  }

  const ENGLISH_COUNTRIES = new Set([
    'US', 'CA', 'GB', 'UK', 'AU', 'NZ', 'IE', 'JM', 'TT', 'BB', 'BS', 'BZ', 'GY', 'AG', 'LC', 'VC', 'GD', 'KN',
  ]);

  const SPANISH_COUNTRIES = new Set([
    'DO', 'MX', 'ES', 'AR', 'CO', 'CL', 'PE', 'VE', 'EC', 'GT', 'CU', 'BO', 'HN', 'PY', 'SV', 'NI', 'CR', 'PA', 'UY', 'PR', 'GQ',
  ]);

  function isManualPreference() {
    return localStorage.getItem(MANUAL_KEY) === '1';
  }

  function detectBrowserLanguage() {
    const browserLang = navigator.language || navigator.userLanguage || 'es';
    const langCode = String(browserLang).split('-')[0].toLowerCase();
    if (menuLanguages.includes(langCode)) return langCode;
    return 'es';
  }

  function languageFromCountry(countryCode) {
    const cc = String(countryCode || '').toUpperCase();
    if (!cc) return null;
    if (ENGLISH_COUNTRIES.has(cc)) return 'en';
    if (SPANISH_COUNTRIES.has(cc)) return 'es';
    return null;
  }

  /** Geo por IP (sin API key). Fallo silencioso → null. */
  async function detectLanguageByGeo() {
    try {
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
      const timer = controller ? setTimeout(() => controller.abort(), 2500) : null;
      const response = await fetch('https://api.country.is/', {
        signal: controller ? controller.signal : undefined,
        cache: 'no-store',
      });
      if (timer) clearTimeout(timer);
      if (!response.ok) return null;
      const data = await response.json();
      return languageFromCountry(data.country);
    } catch {
      return null;
    }
  }

  function getSavedLanguage() {
    const savedLang = localStorage.getItem(STORAGE_KEY);
    if (savedLang && availableLanguages.includes(savedLang)) return savedLang;
    return null;
  }

  function getCurrentLanguage() {
    const saved = getSavedLanguage();
    if (saved) return saved;
    return detectBrowserLanguage();
  }

  async function resolveInitialLanguage() {
    if (isManualPreference()) {
      return getCurrentLanguage();
    }

    const geoLang = await detectLanguageByGeo();
    if (geoLang) {
      localStorage.setItem(STORAGE_KEY, geoLang);
      localStorage.removeItem(MANUAL_KEY);
      return geoLang;
    }

    const browserLang = detectBrowserLanguage();
    localStorage.setItem(STORAGE_KEY, browserLang);
    return browserLang;
  }

  async function loadTranslations(lang) {
    try {
      const response = await fetch(`/locales/${lang}.json`);
      if (!response.ok) throw new Error(`No se pudo cargar ${lang}.json`);
      const data = await response.json();
      return data.translations;
    } catch (error) {
      console.error('Error cargando traducciones:', error);
      return null;
    }
  }

  function translatePage(translations) {
    if (!translations) return;

    currentTranslations = translations;

    document.querySelectorAll('[data-i18n]').forEach((element) => {
      const key = element.getAttribute('data-i18n');
      const translation = getNested(translations, key);
      if (typeof translation === 'string') element.textContent = translation;
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach((element) => {
      const key = element.getAttribute('data-i18n-placeholder');
      const translation = getNested(translations, key);
      if (typeof translation === 'string') element.setAttribute('placeholder', translation);
    });

    const html = document.documentElement;
    const currentLang = localStorage.getItem(STORAGE_KEY) || 'es';
    if (translations.direction === 'rtl') {
      html.setAttribute('dir', 'rtl');
      html.setAttribute('lang', 'ar');
    } else {
      html.setAttribute('dir', 'ltr');
      html.setAttribute('lang', currentLang);
    }
  }

  function updateLanguageDisplay(lang) {
    const selector = document.querySelector('.lang-selector__current');
    if (selector) selector.textContent = lang.toUpperCase();

    document.querySelectorAll('.lang-selector__option').forEach((option) => {
      const active = option.getAttribute('data-lang') === lang;
      option.setAttribute('aria-pressed', active ? 'true' : 'false');
      option.classList.toggle('lang-selector__option--active', active);
    });
  }

  async function setLanguage(lang, options) {
    const opts = options || {};
    if (!availableLanguages.includes(lang)) {
      console.warn('Idioma no disponible:', lang);
      return;
    }

    localStorage.setItem(STORAGE_KEY, lang);
    if (opts.manual) localStorage.setItem(MANUAL_KEY, '1');

    updateLanguageDisplay(lang);

    const translations = await loadTranslations(lang);
    if (translations) {
      translatePage(translations);
      window.dispatchEvent(
        new CustomEvent('cds:language-changed', {
          detail: { language: lang, translations, manual: !!opts.manual },
        })
      );
    }
  }

  function initSelector() {
    const currentLang = getCurrentLanguage();
    updateLanguageDisplay(currentLang);

    const selectorContainer = document.querySelector('.lang-selector');
    if (!selectorContainer) return;

    let dropdown = selectorContainer.querySelector('.lang-selector__dropdown');
    if (!dropdown) {
      dropdown = document.createElement('div');
      dropdown.className = 'lang-selector__dropdown';
      dropdown.setAttribute('role', 'menu');

      menuLanguages.forEach((lang) => {
        const option = document.createElement('button');
        option.className = 'lang-selector__option';
        option.type = 'button';
        option.setAttribute('role', 'menuitem');
        option.setAttribute('data-lang', lang);
        option.textContent = `${lang.toUpperCase()}  ${languageNames[lang]}`;
        option.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          setLanguage(lang, { manual: true });
          dropdown.classList.remove('lang-selector__dropdown--open');
        });
        dropdown.appendChild(option);
      });

      selectorContainer.appendChild(dropdown);
    }

    updateLanguageDisplay(currentLang);

    const button = selectorContainer.querySelector('.lang-selector__button');
    if (button && !button.dataset.cdsLangBound) {
      button.dataset.cdsLangBound = '1';
      button.setAttribute('aria-haspopup', 'true');
      button.setAttribute('aria-expanded', 'false');
      button.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const willOpen = !dropdown.classList.contains('lang-selector__dropdown--open');
        dropdown.classList.toggle('lang-selector__dropdown--open', willOpen);
        button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      });
    }

    if (!document.documentElement.dataset.cdsLangOutside) {
      document.documentElement.dataset.cdsLangOutside = '1';
      document.addEventListener('click', (e) => {
        document.querySelectorAll('.lang-selector').forEach((container) => {
          if (!container.contains(e.target)) {
            const menu = container.querySelector('.lang-selector__dropdown');
            const btn = container.querySelector('.lang-selector__button');
            if (menu) menu.classList.remove('lang-selector__dropdown--open');
            if (btn) btn.setAttribute('aria-expanded', 'false');
          }
        });
      });
    }
  }

  async function init() {
    if (window.__cdsEarlyStyle) {
      window.__cdsEarlyStyle.remove();
      delete window.__cdsEarlyStyle;
    }

    const currentLang = await resolveInitialLanguage();
    document.documentElement.setAttribute('lang', currentLang);

    const translations = await loadTranslations(currentLang);
    if (translations) {
      translatePage(translations);
      window.dispatchEvent(
        new CustomEvent('cds:language-changed', {
          detail: { language: currentLang, translations, manual: false },
        })
      );
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initSelector);
    } else {
      initSelector();
    }
  }

  return {
    init,
    getCurrentLanguage,
    setLanguage,
    getTranslations,
    t,
    availableLanguages: menuLanguages,
  };
})();

LanguageSwitcher.init();
