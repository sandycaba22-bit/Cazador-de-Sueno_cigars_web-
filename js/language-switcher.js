/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema de Internacionalización
 * Detección automática + Selector manual para 6 idiomas
 */

const LanguageSwitcher = (function() {
  // Configuración de idiomas disponibles
  const availableLanguages = ['es', 'en', 'fr', 'zh', 'de', 'ar', 'ru'];
  
  const languageNames = {
    'es': 'Español',
    'en': 'English',
    'fr': 'Français',
    'zh': '中文',
    'de': 'Deutsch',
    'ar': 'العربية',
    'ru': 'Русский'
  };

  const languageFlags = {
    'es': '🇪🇸',
    'en': '🇬🇧',
    'fr': '🇫🇷',
    'zh': '🇨🇳',
    'de': '🇩🇪',
    'ar': '🇸🇦',
    'ru': '🇷🇺'
  };

  // Detección automática del idioma del navegador (Accept-Language)
  function detectBrowserLanguage() {
    const browserLang = navigator.language || navigator.userLanguage;
    const langCode = browserLang.split('-')[0];
    
    if (availableLanguages.includes(langCode)) {
      return langCode;
    }
    
    // Fallback a inglés si no está disponible
    return 'en';
  }

  // Obtener idioma guardado o detectar automáticamente
  function getCurrentLanguage() {
    const savedLang = localStorage.getItem('cds-language');
    if (savedLang && availableLanguages.includes(savedLang)) {
      return savedLang;
    }
    
    const detectedLang = detectBrowserLanguage();
    localStorage.setItem('cds-language', detectedLang);
    return detectedLang;
  }

  // Cargar archivo JSON de traducciones
  async function loadTranslations(lang) {
    try {
      const response = await fetch(`/locales/${lang}.json`);
      if (!response.ok) {
        throw new Error(`No se pudo cargar ${lang}.json`);
      }
      const data = await response.json();
      return data.translations;
    } catch (error) {
      console.error('Error cargando traducciones:', error);
      return null;
    }
  }

  // Traducir elementos con data-i18n
  function translatePage(translations) {
    if (!translations) return;

    // Función recursiva para obtener traducción anidada
    function getTranslation(obj, path) {
      return path.split('.').reduce((o, key) => o && o[key], obj);
    }

    // Traducir elementos con data-i18n
    document.querySelectorAll('[data-i18n]').forEach(element => {
      const key = element.getAttribute('data-i18n');
      const translation = getTranslation(translations, key);
      
      if (translation) {
        element.textContent = translation;
      }
    });

    // Traducir placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
      const key = element.getAttribute('data-i18n-placeholder');
      const translation = getTranslation(translations, key);
      
      if (translation) {
        element.setAttribute('placeholder', translation);
      }
    });

    // Cambiar dirección del documento para árabe
    const html = document.documentElement;
    const currentLang = localStorage.getItem('cds-language') || 'es';
    if (translations.direction === 'rtl') {
      html.setAttribute('dir', 'rtl');
      html.setAttribute('lang', 'ar');
    } else {
      html.setAttribute('dir', 'ltr');
      html.setAttribute('lang', currentLang);
    }
  }

  // Cambiar idioma
  async function setLanguage(lang) {
    if (!availableLanguages.includes(lang)) {
      console.warn('Idioma no disponible:', lang);
      return;
    }
    
    localStorage.setItem('cds-language', lang);
    updateLanguageDisplay(lang);
    
    // Cargar y aplicar traducciones
    const translations = await loadTranslations(lang);
    if (translations) {
      translatePage(translations);
      console.log('Idioma cambiado a:', lang);
      
      // Emitir evento para que otros scripts puedan reaccionar
      const event = new CustomEvent('cds:language-changed', {
        detail: { language: lang, translations }
      });
      window.dispatchEvent(event);
    }
  }

  // Actualizar display del selector
  function updateLanguageDisplay(lang) {
    const selector = document.querySelector('.lang-selector__current');
    if (selector) {
      selector.textContent = `${languageFlags[lang]} ${languageNames[lang]}`;
    }
  }

  // Inicializar selector
  function initSelector() {
    const currentLang = getCurrentLanguage();
    updateLanguageDisplay(currentLang);
    
    // Crear dropdown
    const selectorContainer = document.querySelector('.lang-selector');
    if (!selectorContainer) return;

    const dropdown = document.createElement('div');
    dropdown.className = 'lang-selector__dropdown';
    
    availableLanguages.forEach(lang => {
      const option = document.createElement('button');
      option.className = 'lang-selector__option';
      option.textContent = `${languageFlags[lang]} ${languageNames[lang]}`;
      option.setAttribute('data-lang', lang);
      option.onclick = () => setLanguage(lang);
      dropdown.appendChild(option);
    });

    selectorContainer.appendChild(dropdown);

    // Toggle dropdown
    const button = selectorContainer.querySelector('.lang-selector__button');
    if (button) {
      button.onclick = () => {
        dropdown.classList.toggle('lang-selector__dropdown--open');
      };
    }

    // Cerrar dropdown al hacer clic fuera
    document.addEventListener('click', (e) => {
      if (!selectorContainer.contains(e.target)) {
        dropdown.classList.remove('lang-selector__dropdown--open');
      }
    });
  }

  // Inicialización
  async function init() {
    // Remover estilo oculto del script temprano
    if (window.__cdsEarlyStyle) {
      window.__cdsEarlyStyle.remove();
      delete window.__cdsEarlyStyle;
    }
    
    // Cargar traducciones automáticamente
    const currentLang = getCurrentLanguage();
    const translations = await loadTranslations(currentLang);
    if (translations) {
      translatePage(translations);
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
    availableLanguages
  };
})();

// Auto-inicialización
LanguageSwitcher.init();
