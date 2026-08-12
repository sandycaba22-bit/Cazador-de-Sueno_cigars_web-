/**
 * Restaura la visibilidad del body cuando language-detect-early.js
 * ocultó la página pero no se cargó language-switcher.js (p. ej. checkout).
 */
(function () {
  'use strict';

  function revealPage() {
    if (window.__cdsEarlyStyle) {
      window.__cdsEarlyStyle.remove();
      delete window.__cdsEarlyStyle;
    }

    document.documentElement.style.visibility = 'visible';
    document.body.style.visibility = 'visible';
  }

  window.revealCdsPage = revealPage;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', revealPage);
  } else {
    revealPage();
  }
})();
