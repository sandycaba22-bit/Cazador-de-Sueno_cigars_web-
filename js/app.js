/**
 * Página principal — catálogo y selección caja / puro suelto.
 */

function catalogT(path, fallback) {
  if (typeof LanguageSwitcher !== 'undefined' && typeof LanguageSwitcher.t === 'function') {
    const value = LanguageSwitcher.t(`home.catalog.${path}`);
    if (value) return value;
  }
  return fallback;
}

function localizedProductName(product) {
  const lang =
    (typeof LanguageSwitcher !== 'undefined' && LanguageSwitcher.getCurrentLanguage
      ? LanguageSwitcher.getCurrentLanguage()
      : null) ||
    localStorage.getItem('cds-language') ||
    'es';
  if (lang === 'en' && product.nameEn) return product.nameEn;
  return product.name;
}

function renderProductCard(product) {
  const unitsLabel = catalogT('units_per_box', 'uds/caja');
  const rangoBadge = isRangoLine(product.line)
    ? `<span class="badge badge--rango">Rango · ${PACKAGING.RANGO_UNITS} ${unitsLabel}</span>`
    : `<span class="badge badge--standard">${PACKAGING.STANDARD_UNITS} ${unitsLabel}</span>`;

  const maxLoose = product.stockUnits;
  const maxBoxes = product.stockBoxes;
  const name = localizedProductName(product);
  const stock = catalogT('stock', '{units} puros disponibles ({boxes} cajas)')
    .replace('{units}', String(product.stockUnits))
    .replace('{boxes}', String(product.stockBoxes));

  return `
    <article class="product-card" data-id="${product.id}">
      <div class="product-card__image">
        <a href="${product.href || '#catalogo'}" class="product-card__photo" aria-label="${escapeHtml(name)}">
          <img src="${product.image}" alt="${escapeHtml(name)}" loading="lazy" width="280" height="200" />
        </a>
        ${rangoBadge}
      </div>
      <div class="product-card__body">
        <p class="product-card__origin">${escapeHtml(product.origin)} · ${escapeHtml(product.strength)}</p>
        <h3 class="product-card__title"><a href="${product.href || '#catalogo'}">${escapeHtml(name)}</a></h3>
        <p class="product-card__desc">${escapeHtml(product.description)}</p>
        <div class="product-card__pricing">
          <span class="product-card__price">${formatCurrency(product.pricePerBox)}</span>
          <span class="product-card__unit">${formatCurrency(product.pricePerUnit)}${escapeHtml(catalogT('per_unit', '/ud.'))}</span>
        </div>
        <p class="product-card__stock">${escapeHtml(stock)}</p>
        <div class="product-card__format">
          <label class="format-option">
            <input type="radio" name="format-${product.id}" value="box" checked />
            ${escapeHtml(catalogT('box', 'Caja'))}
          </label>
          <label class="format-option">
            <input type="radio" name="format-${product.id}" value="unit" />
            ${escapeHtml(catalogT('loose', 'Puro suelto'))}
          </label>
        </div>
        <div class="product-card__actions">
          <label class="qty-label">
            <span class="qty-label-text">${escapeHtml(catalogT('qty', 'Cantidad'))}</span>
            <input type="number" class="qty-input" min="1" max="${maxBoxes}" value="1" aria-label="${escapeHtml(catalogT('qty', 'Cantidad'))}" data-max-boxes="${maxBoxes}" data-max-units="${maxLoose}" />
          </label>
          <button type="button" class="btn btn--primary add-to-cart-btn" ${product.inStock ? '' : 'disabled'}>
            ${escapeHtml(catalogT('add', 'Añadir al carrito'))}
          </button>
        </div>
      </div>
    </article>
  `;
}

function bindCatalogEvents() {
  const grid = $('#catalog-grid');
  if (!grid || grid.dataset.cdsCatalogBound === '1') return;
  grid.dataset.cdsCatalogBound = '1';

  grid.addEventListener('change', (e) => {
    const radio = e.target.closest('input[type="radio"][name^="format-"]');
    if (!radio) return;
    const card = radio.closest('.product-card');
    const qtyInput = card.querySelector('.qty-input');
    const isBox = radio.value === 'box';
    qtyInput.max = isBox ? qtyInput.dataset.maxBoxes : qtyInput.dataset.maxUnits;
    qtyInput.value = 1;
    card.querySelector('.qty-label-text').textContent = isBox
      ? catalogT('qty_boxes', 'Cajas')
      : catalogT('qty_loose', 'Puros sueltos');
  });

  grid.addEventListener('click', (e) => {
    const btn = e.target.closest('.add-to-cart-btn');
    if (!btn) return;

    const card = btn.closest('.product-card');
    const productId = card.dataset.id;
    const qtyInput = card.querySelector('.qty-input');
    const unitType =
      card.querySelector('input[name^="format-"]:checked')?.value === 'unit'
        ? UNIT_TYPES.UNIT
        : UNIT_TYPES.BOX;

    const result = addToCart(productId, qtyInput.value, unitType);

    if (result.success) {
      const added =
        (typeof LanguageSwitcher !== 'undefined' && LanguageSwitcher.t
          ? LanguageSwitcher.t('home.catalog.added')
          : null) || 'Añadido al carrito. Tu selección se mantiene al seguir navegando.';
      showToast(added, 'success');
      updateCartUI();
      const drawer = $('#cart-drawer');
      if (drawer && window.innerWidth > 900) {
        drawer.classList.add('is-open');
        $('#cart-overlay')?.classList.add('is-visible');
      }
    } else {
      showToast(result.error, 'error');
    }
  });
}

function renderCatalog() {
  const grid = $('#catalog-grid');
  if (!grid) return;
  grid.innerHTML = getCatalog().map(renderProductCard).join('');
  bindCatalogEvents();
}

function initHomePage() {
  renderCatalog();
  initGlobalCart();
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.body.dataset.page === 'home') {
    initHomePage();
  }
});

window.addEventListener('cds:language-changed', () => {
  if (document.body.dataset.page === 'home') {
    renderCatalog();
  }
});
