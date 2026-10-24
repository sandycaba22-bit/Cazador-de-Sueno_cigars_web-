/**
 * Detección temprana de idioma (antes del pintado).
 * Respeta preferencia manual en localStorage; si no hay, usa el idioma
 * guardado automáticamente o el del navegador (ES/EN).
 * La geolocalización por IP la completa language-switcher.js al cargar.
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'cds-language';
  const MANUAL_KEY = 'cds-language-manual';
  const menuLanguages = ['es', 'en'];

  function detectBrowserLanguage() {
    const browserLang = navigator.language || navigator.userLanguage || 'es';
    const langCode = String(browserLang).split('-')[0].toLowerCase();
    if (menuLanguages.includes(langCode)) return langCode;
    return 'es';
  }

  function getCurrentLanguage() {
    const savedLang = localStorage.getItem(STORAGE_KEY);
    if (savedLang && menuLanguages.includes(savedLang)) return savedLang;
    if (localStorage.getItem(MANUAL_KEY) === '1' && savedLang) return savedLang;
    return detectBrowserLanguage();
  }

  const currentLang = getCurrentLanguage();
  document.documentElement.setAttribute('lang', currentLang);
  document.documentElement.setAttribute('dir', 'ltr');

  const skipHidePages = /checkout\.html|order-confirmation\.html/i;
  if (!skipHidePages.test(location.pathname)) {
    const style = document.createElement('style');
    style.textContent = 'body { visibility: hidden; }';
    document.head.appendChild(style);
    window.__cdsEarlyStyle = style;
  }
})();
