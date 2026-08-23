/**
 * UI compartida del carrito — persiste y sincroniza en todas las páginas.
 */

function cartTt(path, fallback) {
  try {
    if (typeof LanguageSwitcher !== 'undefined' && typeof LanguageSwitcher.t === 'function') {
      const value = LanguageSwitcher.t(path);
      if (typeof value === 'string' && value) return value;
    }
  } catch (_) {
    /* ignore */
  }
  return fallback;
}

function renderMiniCartItem(item) {
  const typeLabel =
    item.unitType === UNIT_TYPES.BOX
      ? cartTt('home.cart.box_label', 'caja(s)')
      : cartTt('home.cart.loose_label', 'sueltos');
  const unitsLabel = cartTt('home.cart.units', 'uds.');
  const unitsPerBox = cartTt('home.cart.units_per_box', 'uds/caja');
  const rangoBadge = cartTt('home.cart.rango_badge', 'Rango');
  const lineClass = isRangoLine(item.product.line) ? 'is-rango' : 'is-standard';
  const packagingBadge = isRangoLine(item.product.line)
    ? `<span class="badge badge--rango badge--inline">${rangoBadge} · ${PACKAGING.RANGO_UNITS} ${unitsLabel}</span>`
    : `<span class="badge badge--standard badge--inline">${PACKAGING.STANDARD_UNITS} ${unitsPerBox}</span>`;
  const thumb = item.product.image
    ? `<img class="mini-cart__thumb" src="${escapeHtml(item.product.image)}" alt="" loading="lazy" />`
    : '';

  return `
    <li class="mini-cart__item ${lineClass}" data-line-id="${escapeHtml(item.lineId)}">
      ${thumb}
      <div class="mini-cart__item-info">
        <strong>${escapeHtml(item.product.name)}</strong>
        ${packagingBadge}
        <span>${item.quantity} ${typeLabel} · ${item.totalUnits} ${unitsLabel}</span>
        <div class="mini-cart__qty-controls">
          <button type="button" class="btn-qty" data-action="decrease" aria-label="${escapeHtml(cartTt('home.cart.decrease', 'Reducir cantidad'))}">−</button>
          <span class="mini-cart__qty">${item.quantity}</span>
          <button type="button" class="btn-qty" data-action="increase" aria-label="${escapeHtml(cartTt('home.cart.increase', 'Aumentar cantidad'))}">+</button>
        </div>
      </div>
      <div class="mini-cart__item-actions">
        <span>${formatCurrency(item.lineTotal)}</span>
        <button type="button" class="btn-icon remove-cart-item" aria-label="${escapeHtml(cartTt('home.cart.remove', 'Eliminar'))}">×</button>
      </div>
    </li>
  `;
}

function updateCartUI() {
  const countEl = $('#cart-count');
  const itemsEl = $('#mini-cart-items');
  const subtotalEl = $('#mini-cart-subtotal');
  const checkoutLink = $('#go-checkout');
  const linesEl = $('#cart-line-count');

  const items = getCartItems();
  const unitCount = getCartCount();
  const subtotal = items.reduce((s, i) => s + i.lineTotal, 0);

  if (countEl) countEl.textContent = String(unitCount);
  if (linesEl) linesEl.textContent = String(items.length);
  if (itemsEl) {
    itemsEl.innerHTML = items.length
      ? items.map(renderMiniCartItem).join('')
      : `<li class="mini-cart__empty">${cartTt('home.cart.empty', 'Tu carrito está vacío.')}</li>`;
  }
  if (subtotalEl) subtotalEl.textContent = formatCurrency(subtotal);
  if (checkoutLink) {
    checkoutLink.classList.toggle('btn--disabled', items.length === 0);
    checkoutLink.setAttribute('aria-disabled', items.length === 0 ? 'true' : 'false');
  }
}

function initCartDrawer() {
  const toggle = $('#cart-toggle');
  const drawer = $('#cart-drawer');
  const overlay = $('#cart-overlay');
  const closeBtn = $('#cart-close');

  if (!drawer) return;

  function open() {
    drawer.classList.add('is-open');
    overlay?.classList.add('is-visible');
    document.body.classList.add('no-scroll');
    toggle?.setAttribute('aria-expanded', 'true');
    updateCartUI();
  }

  function close() {
    drawer.classList.remove('is-open');
    overlay?.classList.remove('is-visible');
    document.body.classList.remove('no-scroll');
    toggle?.setAttribute('aria-expanded', 'false');
  }

  toggle?.addEventListener('click', open);
  closeBtn?.addEventListener('click', close);
  overlay?.addEventListener('click', close);

  drawer.addEventListener('click', (e) => {
    const removeBtn = e.target.closest('.remove-cart-item');
    if (removeBtn) {
      const item = removeBtn.closest('.mini-cart__item');
      removeFromCart(item.dataset.lineId);
      updateCartUI();
      showToast(cartTt('home.cart.removed', 'Artículo eliminado.'), 'info');
      return;
    }

    const qtyBtn = e.target.closest('.btn-qty');
    if (qtyBtn) {
      const item = qtyBtn.closest('.mini-cart__item');
      const lineId = item.dataset.lineId;
      const current = getCartItems().find((i) => i.lineId === lineId);
      if (!current) return;

      const delta = qtyBtn.dataset.action === 'increase' ? 1 : -1;
      const result = updateCartQuantity(lineId, current.quantity + delta);
      if (result.success) {
        updateCartUI();
      } else {
        showToast(result.error, 'error');
      }
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });
}

function initGlobalCart() {
  initCartPersistence();
  initCartDrawer();
  updateCartUI();
  window.addEventListener('cart:updated', updateCartUI);
  window.addEventListener('cds:language-changed', updateCartUI);
}
