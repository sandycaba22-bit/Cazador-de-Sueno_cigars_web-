/**
 * Scripts compartidos — páginas individuales de vitolas
 */
(function () {
  'use strict';

  async function renderLogos() {
    if (!window.LogoRender) return;
    document.querySelectorAll('.logo-canvas').forEach(async (canvas) => {
      try {
        const h = parseInt(canvas.dataset.height, 10) || 44;
        await LogoRender.renderPdfToCanvas(canvas, canvas.dataset.logo, h);
        canvas.classList.add('logo-canvas--ready');
      } catch (e) {
        console.warn('Logo render failed:', e);
      }
    });
  }

  function initReveal() {
    const revealEls = document.querySelectorAll('.reveal');
    if (!revealEls.length) return;
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('reveal--visible');
            io.unobserve(entry.target);
          }
        });
      }, { threshold: 0.1 });
      revealEls.forEach((el) => io.observe(el));
    } else {
      revealEls.forEach((el) => el.classList.add('reveal--visible'));
    }
  }

  // Función para re-renderizar traducciones de vitolas
  function translateVitolaPage(translations) {
    if (!translations) return;

    // Función recursiva para obtener traducción anidada
    function getTranslation(obj, path) {
      return path.split('.').reduce((o, key) => o && o[key], obj);
    }

    // Traducir elementos con data-i18n en la página de vitola
    document.querySelectorAll('[data-i18n]').forEach(element => {
      const key = element.getAttribute('data-i18n');
      const translation = getTranslation(translations, key);
      
      if (translation) {
        element.textContent = translation;
      }
    });
  }

  // Escuchar cambios de idioma para re-renderizar contenido dinámico
  function initLanguageListener() {
    window.addEventListener('cds:language-changed', (event) => {
      const { translations } = event.detail;
      translateVitolaPage(translations);
      console.log('Vitola page re-rendered for language change');
    });
  }

  function onReady() {
    renderLogos();
    initReveal();
    initLanguageListener();
  }

  if (localStorage.getItem('cds-age-verified') === '1') {
    onReady();
  } else {
    window.addEventListener('cds:age-verified', onReady, { once: true });
  }
})();
