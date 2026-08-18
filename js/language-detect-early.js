/**
 * CAZADOR DE SUEÑOS CIGARS - Detección Temprana de Idioma
 * Ejecuta inmediatamente para evitar parpadeos visuales
 * Debe incluirse en el <head> antes de cualquier contenido visible
 */

(function() {
  'use strict';
  
  const availableLanguages = ['es', 'en', 'fr', 'zh', 'de', 'ar', 'ru'];
  const STORAGE_KEY = 'cds-language';
  
  // Detectar idioma del navegador
  function detectBrowserLanguage() {
    const browserLang = navigator.language || navigator.userLanguage;
    const langCode = browserLang.split('-')[0];
    
    if (availableLanguages.includes(langCode)) {
      return langCode;
    }
    
    // Fallback a inglés
    return 'en';
  }
  
  // Obtener idioma actual con prioridad: manual > detectado
  function getCurrentLanguage() {
    const savedLang = localStorage.getItem(STORAGE_KEY);
    if (savedLang && availableLanguages.includes(savedLang)) {
      return savedLang;
    }
    
    const detectedLang = detectBrowserLanguage();
    localStorage.setItem(STORAGE_KEY, detectedLang);
    return detectedLang;
  }
  
  // Aplicar idioma inmediatamente
  const currentLang = getCurrentLanguage();
  
  // Establecer atributo lang en HTML
  document.documentElement.setAttribute('lang', currentLang);
  
  // Establecer dirección para RTL
  if (currentLang === 'ar') {
    document.documentElement.setAttribute('dir', 'rtl');
  } else {
    document.documentElement.setAttribute('dir', 'ltr');
  }
  
  // Prevenir parpadeo ocultando el body temporalmente
  // El script principal lo mostrará después de cargar traducciones
  const skipHidePages = /checkout\.html|order-confirmation\.html|cart-test\.html/i;
  if (!skipHidePages.test(location.pathname)) {
    const style = document.createElement('style');
    style.textContent = 'body { visibility: hidden; }';
    document.head.appendChild(style);
    window.__cdsEarlyStyle = style;
  }
  
  console.log('[CDS] Idioma detectado:', currentLang);
})();
