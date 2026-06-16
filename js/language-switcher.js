/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema de Internacionalización
 * Detección automática + Selector manual para 6 idiomas
 */

const LanguageSwitcher = (function() {
  // Configuración de idiomas disponibles
  const availableLanguages = ['es', 'en', 'fr', 'zh', 'de', 'ar'];
  
  const languageNames = {
    'es': 'Español',
    'en': 'English',
    'fr': 'Français',
    'zh': '中文',
    'de': 'Deutsch',
    'ar': 'العربية'
  };

  const languageFlags = {
    'es': '🇪🇸',
    'en': '🇬🇧',
    'fr': '🇫🇷',
    'zh': '🇨🇳',
    'de': '🇩🇪',
    'ar': '🇸🇦'
  };

  // Detección automática del idioma del navegador
  function detectBrowserLanguage() {
    const browserLang = navigator.language || navigator.userLanguage;
    const langCode = browserLang.split('-')[0];
    
    if (availableLanguages.includes(langCode)) {
      return langCode;
    }
    
    // Fallback a español si no está disponible
    return 'es';
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

  // Cambiar idioma
  function setLanguage(lang) {
    if (!availableLanguages.includes(lang)) {
      console.warn('Idioma no disponible:', lang);
      return;
    }
    
    localStorage.setItem('cds-language', lang);
    updateLanguageDisplay(lang);
    
    // Aquí se implementaría la lógica para cambiar el contenido
    // Por ahora solo actualizamos el estado
    console.log('Idioma cambiado a:', lang);
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
  function init() {
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
