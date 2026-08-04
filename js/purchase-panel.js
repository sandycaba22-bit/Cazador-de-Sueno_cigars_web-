/**
 * CAZADOR DE SUEÑOS CIGARS - Luxury Purchase Panel
 * Handles purchase panel interactions with shopping cart and lock system
 */

(function() {
  'use strict';

  console.log('Purchase Panel Script Loading...');

  function init() {
    console.log('Init called, ShoppingCart available:', !!window.ShoppingCart);

    if (!window.ShoppingCart) {
      console.log('ShoppingCart not ready, retrying in 100ms...');
      setTimeout(init, 100);
      return;
    }

    console.log('ShoppingCart ready, setting up purchase panels...');
    setupPurchasePanels();
    setupCartLockListeners();
  }

  function isValidPurchaseButton(button) {
    return button instanceof HTMLElement && document.body.contains(button);
  }

  function isClickBlocked(button) {
    if (!isValidPurchaseButton(button)) {
      return true;
    }

    const computedStyle = window.getComputedStyle(button);
    return button.disabled || computedStyle.pointerEvents === 'none';
  }

  function getButtonLabel(button) {
    if (!isValidPurchaseButton(button)) {
      return null;
    }

    return button.querySelector('span');
  }

  function setupPurchasePanels() {
    const purchaseButtons = document.querySelectorAll('.purchase-panel__button');
    console.log('Found purchase buttons:', purchaseButtons.length);

    purchaseButtons.forEach((button, index) => {
      if (!isValidPurchaseButton(button)) {
        console.warn('Skipping invalid purchase button at index:', index);
        return;
      }

      console.log(`Button ${index}: productId=${button.dataset.productId}, quantity=${button.dataset.quantity}`);
      button.removeEventListener('click', handlePurchaseClick);
      button.addEventListener('click', handlePurchaseClick);
    });
  }

  function setupCartLockListeners() {
    window.addEventListener('cds:cart-locked', updateButtonsLockState);
    window.addEventListener('cds:cart-unlocked', updateButtonsLockState);
    updateButtonsLockState();
  }

  function updateButtonsLockState() {
    const isLocked = ShoppingCart.isCartLocked();
    const purchaseButtons = document.querySelectorAll('.purchase-panel__button');
    console.log('Updating buttons lock state, isLocked:', isLocked);

    purchaseButtons.forEach(button => {
      if (!isValidPurchaseButton(button)) {
        return;
      }

      const span = getButtonLabel(button);

      if (isLocked) {
        button.classList.add('purchase-panel__button--locked');
        button.disabled = true;
        button.setAttribute('data-locked', 'true');

        if (span) {
          span.textContent = 'Carrito Bloqueado';
        }

        return;
      }

      button.classList.remove('purchase-panel__button--locked');
      button.disabled = false;
      button.removeAttribute('data-locked');

      if (span) {
        const originalText = button.dataset.originalText ||
          (button.classList.contains('purchase-panel__button--unit') ? 'Agregar Unidad' : 'Agregar Caja');

        if (!button.dataset.originalText) {
          button.dataset.originalText = originalText;
        }

        span.textContent = originalText;
      }
    });
  }

  async function handlePurchaseClick(e) {
    e.preventDefault();

    const button = e.currentTarget;
    const isBlueButton = isValidPurchaseButton(button) &&
      button.classList.contains('purchase-panel__button--unit');

    if (isBlueButton) {
      console.log('Botón azul presionado');
    }

    if (!isValidPurchaseButton(button)) {
      console.error('Purchase button event fired without a valid DOM element');
      return;
    }

    if (isClickBlocked(button)) {
      console.warn('Click bloqueado: el botón está disabled o tiene pointer-events: none');
      return;
    }

    const label = getButtonLabel(button);
    const productId = button.dataset.productId;
    const quantity = parseInt(button.dataset.quantity, 10) || 1;
    const originalText = button.dataset.originalText || (label ? label.textContent : button.textContent);

    if (!button.dataset.originalText) {
      button.dataset.originalText = originalText;
    }

    console.log('Purchase click - productId:', productId, 'quantity:', quantity);

    if (!productId) {
      console.error('Product ID not found on button');
      showToast('❌ Error: Product ID no encontrado en el botón', 'error');
      return;
    }

    if (ShoppingCart.isCartLocked()) {
      console.log('Cart is locked, showing notification');
      showLockNotification(button);
      showToast('🔒 Carrito bloqueado tras pago', 'error');
      return;
    }

    button.disabled = true;
    if (label) {
      label.textContent = 'Agregando...';
    }

    try {
      const success = await Promise.resolve(ShoppingCart.addToCart(productId, quantity));
      console.log('Add to cart result:', success);

      if (success) {
        if (label) {
          label.textContent = '¡Agregado!';
        }

        button.style.background = 'linear-gradient(135deg, #2d5a3d 0%, #1a3d2a 100%)';
        showToast('✅ ¡Agregado al carrito con éxito!', 'success');

        setTimeout(() => {
          button.disabled = false;
          if (label) {
            label.textContent = originalText;
          }
          button.style.background = '';
        }, 1500);

        updateCartBadge();
        return;
      }

      button.disabled = false;
      if (label) {
        label.textContent = 'Error - Reintentar';
      }

      showToast('❌ Error: No se pudo agregar al carrito', 'error');

      setTimeout(() => {
        if (label) {
          label.textContent = originalText;
        }
      }, 2000);
    } catch (error) {
      console.error('Error adding to cart:', error);
      button.disabled = false;

      if (label) {
        label.textContent = 'Error - Reintentar';
      }

      showToast('❌ Error: ' + error.message, 'error');

      setTimeout(() => {
        if (label) {
          label.textContent = originalText;
        }
      }, 2000);
    }
  }

  function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'cart-toast cart-toast--' + type;
    toast.innerHTML = message;
    toast.style.cssText = `
      position: fixed;
      top: 100px;
      right: 20px;
      background: ${type === 'success' ? '#2d5a3d' : '#8B0000'};
      color: #fff;
      padding: 1rem 1.5rem;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      z-index: 10000;
      font-family: 'Libre Baskerville', Georgia, serif;
      font-size: 1rem;
      font-weight: 500;
      border: 2px solid ${type === 'success' ? '#4caf50' : '#FFD700'};
      animation: slideIn 0.3s ease-out;
      max-width: 300px;
    `;

    const style = document.createElement('style');
    style.textContent = `
      @keyframes slideIn {
        from {
          transform: translateX(100%);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }
    `;

    document.head.appendChild(style);
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease-in forwards';
      setTimeout(() => {
        toast.remove();
        style.remove();
      }, 300);
    }, 3000);
  }

  function showLockNotification(button) {
    const notification = document.createElement('div');
    notification.className = 'purchase-lock-notification';
    notification.innerHTML = `
      <div class="purchase-lock-tooltip">
        <span class="lock-icon">🔒</span>
        <span>Carrito bloqueado tras pago</span>
      </div>
    `;

    const rect = button.getBoundingClientRect();
    notification.style.position = 'fixed';
    notification.style.top = `${rect.bottom + 10}px`;
    notification.style.left = `${rect.left}px`;
    notification.style.zIndex = '1000';
    document.body.appendChild(notification);

    setTimeout(() => {
      notification.remove();
    }, 2000);
  }

  function updateCartBadge() {
    const cart = ShoppingCart.getCart();
    const badge = document.querySelector('.cart-button__badge, .cart-badge');

    if (badge) {
      const totalItems = cart.items.reduce((sum, item) => sum + item.quantity, 0);
      badge.textContent = totalItems > 0 ? totalItems : '';
      badge.style.display = totalItems > 0 ? 'flex' : 'none';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.addEventListener('cds:cart-updated', updateCartBadge);
})();

