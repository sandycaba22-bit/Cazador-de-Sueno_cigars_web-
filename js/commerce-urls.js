/**
 * Rutas absolutas de comercio — evita checkout.html roto desde /vitolas/.
 */
(function () {
  'use strict';

  function getSiteRoot() {
    const meta = document.querySelector('meta[name="site-root"]');
    if (meta && meta.content) {
      const value = String(meta.content).trim();
      if (value === '/' || value === '') return '/';
      return value.replace(/\/?$/, '/');
    }
    if (/\/vitolas\//i.test(location.pathname)) return '/';
    return '/';
  }

  function getCheckoutUrl() {
    const root = getSiteRoot();
    return root === '/' ? '/checkout.html' : `${root}checkout.html`;
  }

  function resolveAssetUrl(path) {
    if (!path) return path;
    if (/^https?:\/\//i.test(path) || path.startsWith('/')) return path;
    return `/${path.replace(/^\.\//, '')}`;
  }

  window.getCheckoutUrl = getCheckoutUrl;
  window.resolveCommerceAssetUrl = resolveAssetUrl;
})();
