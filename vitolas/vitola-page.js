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

  function initCommerceFloats() {
    if (document.body.dataset.page === 'checkout') return;
    if (document.getElementById('cds-float-whatsapp')) return;

    var phone = '18095550198';
    var wa = document.createElement('a');
    wa.id = 'cds-float-whatsapp';
    wa.className = 'cds-float-whatsapp';
    wa.href = 'https://wa.me/' + phone;
    wa.target = '_blank';
    wa.rel = 'noopener';
    wa.setAttribute('aria-label', 'WhatsApp');
    wa.innerHTML = '<span class="cds-float-whatsapp__icon">💬</span><span class="cds-float-whatsapp__text">WhatsApp</span>';
    document.body.appendChild(wa);

    // Un solo carrito flotante por página: la calculadora ya monta el suyo.
    if (!document.getElementById('cs-carrito-flotante') && !document.getElementById('cds-float-cart')) {
      var cart = document.createElement('a');
      cart.id = 'cds-float-cart';
      cart.className = 'cds-float-cart';
      cart.href = typeof getCheckoutUrl === 'function' ? getCheckoutUrl() : '/checkout.html';
      cart.setAttribute('aria-label', 'Ir al checkout');
      cart.innerHTML = '<span class="cds-float-cart__icon">🛒</span><span id="cds-float-cart-count" class="cds-float-cart__count">0</span>';
      document.body.appendChild(cart);
    }

    function refreshCount() {
      var count = 0;
      try {
        if (window.ShoppingCart && window.ShoppingCart.getCart) {
          count = window.ShoppingCart.getCart().items.reduce(function (s, i) { return s + i.quantity; }, 0);
        }
      } catch (e) { /* ignore */ }
      var el = document.getElementById('cds-float-cart-count');
      if (el) el.textContent = String(count);
    }

    refreshCount();
    window.addEventListener('cds:cart-updated', refreshCount);
  }

  function onReady() {
    renderLogos();
    initReveal();
    initLanguageListener();
    initCommerceFloats();
  }

  function isAgeVerified() {
    if (document.cookie.indexOf('cds_age_gate=accepted') !== -1) {
      return true;
    }

    try {
      return localStorage.getItem('cds-age-verified') === '1';
    } catch (error) {
      return false;
    }
  }

  if (isAgeVerified()) {
    onReady();
  } else {
    window.addEventListener('cds:age-verified', onReady, { once: true });
  }
})();
