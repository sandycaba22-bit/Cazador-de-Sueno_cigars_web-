/**
 * CAZADOR DE SUEÑOS CIGARS - Luxury Purchase Panel
 * Handles purchase panel interactions with shopping cart and lock system
 */

(function() {
  'use strict';

  // Wait for DOM and ShoppingCart to be ready
  function init() {
    if (!window.ShoppingCart) {
      setTimeout(init, 100);
      return;
    }

    setupPurchasePanels();
    setupCartLockListeners();
  }

  function setupPurchasePanels() {
    const purchaseButtons = document.querySelectorAll('.purchase-panel__button');
    
    purchaseButtons.forEach(button => {
      button.addEventListener('click', handlePurchaseClick);
    });
  }

  function setupCartLockListeners() {
    // Escuchar eventos de bloqueo/desbloqueo del carrito
    window.addEventListener('cds:cart-locked', updateButtonsLockState);
    window.addEventListener('cds:cart-unlocked', updateButtonsLockState);
    
    // Estado inicial
    updateButtonsLockState();
  }

  function updateButtonsLockState() {
    const isLocked = ShoppingCart.isCartLocked();
    const purchaseButtons = document.querySelectorAll('.purchase-panel__button');
    
    purchaseButtons.forEach(button => {
      if (isLocked) {
        button.classList.add('purchase-panel__button--locked');
        button.disabled = true;
        button.setAttribute('data-locked', 'true');
        
        // Cambiar texto visualmente
        const span = button.querySelector('span');
        if (span) {
          span.textContent = 'Carrito Bloqueado';
        }
      } else {
        button.classList.remove('purchase-panel__button--locked');
        button.disabled = false;
        button.removeAttribute('data-locked');
        
        // Restaurar texto original
        const span = button.querySelector('span');
        if (span) {
          const originalText = button.dataset.originalText || 
                            (button.classList.contains('purchase-panel__button--unit') ? 'Agregar Unidad' : 'Agregar Caja');
          if (!button.dataset.originalText) {
            button.dataset.originalText = originalText;
          }
          span.textContent = originalText;
        }
      }
    });
  }

  async function handlePurchaseClick(e) {
    const button = e.currentTarget;
    const productId = button.dataset.productId;
    const quantity = parseInt(button.dataset.quantity) || 1;

    if (!productId) {
      console.error('Product ID not found on button');
      return;
    }

    // Verificar bloqueo del carrito
    if (ShoppingCart.isCartLocked()) {
      showLockNotification(button);
      return;
    }

    // Visual feedback
    const originalText = button.querySelector('span').textContent;
    button.disabled = true;
    button.querySelector('span').textContent = 'Agregando...';

    try {
      // Add to cart
      const success = ShoppingCart.addToCart(productId, quantity);
      
      if (success) {
        // Success feedback
        button.querySelector('span').textContent = '¡Agregado!';
        button.style.background = 'linear-gradient(135deg, #2d5a3d 0%, #1a3d2a 100%)';
        
        // Reset after delay
        setTimeout(() => {
          button.disabled = false;
          button.querySelector('span').textContent = originalText;
          button.style.background = '';
        }, 1500);

        // Update cart badge
        updateCartBadge();
      } else {
        // Error feedback
        button.disabled = false;
        button.querySelector('span').textContent = 'Error - Reintentar';
        
        setTimeout(() => {
          button.querySelector('span').textContent = originalText;
        }, 2000);
      }

    } catch (error) {
      console.error('Error adding to cart:', error);
      button.disabled = false;
      button.querySelector('span').textContent = 'Error - Reintentar';
      
      setTimeout(() => {
        button.querySelector('span').textContent = originalText;
      }, 2000);
    }
  }

  function showLockNotification(button) {
    // Crear notificación flotante cerca del botón
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
    const badge = document.querySelector('.cart-button__badge');
    
    if (badge) {
      const totalItems = cart.items.reduce((sum, item) => sum + item.quantity, 0);
      badge.textContent = totalItems > 0 ? totalItems : '';
      badge.style.display = totalItems > 0 ? 'flex' : 'none';
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Also listen for cart updates
  window.addEventListener('cds:cart-updated', updateCartBadge);

})();
