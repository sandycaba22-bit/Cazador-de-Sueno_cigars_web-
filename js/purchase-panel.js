/**
 * CAZADOR DE SUEÑOS CIGARS - Luxury Purchase Panel
 * Handles purchase panel interactions with shopping cart
 */

(function() {
  'use strict';

  function setupPurchasePanels() {
    const purchaseButtons = document.querySelectorAll('.purchase-panel__button');
    
    purchaseButtons.forEach(button => {
      button.addEventListener('click', handlePurchaseClick);
    });
  }

  function handlePurchaseClick(e) {
    const button = e.currentTarget;
    const productId = button.dataset.productId;
    const quantity = parseInt(button.dataset.quantity) || 1;

    if (!productId) {
      console.error('Product ID not found on button');
      return;
    }

    if (!window.ShoppingCart) {
      console.error('ShoppingCart not available');
      return;
    }

    // Visual feedback
    const originalText = button.querySelector('span').textContent;
    button.disabled = true;
    button.querySelector('span').textContent = 'Agregando...';

    try {
      // Add to cart (synchronous call)
      const success = window.ShoppingCart.addToCart(productId, quantity);
      
      if (success) {
        // Success feedback
        button.querySelector('span').textContent = '¡Agregado!';
        button.style.background = 'linear-gradient(135deg, #2d5a3d 0%, #1a3d2a 100%)';
        
        showCheckoutShortcut(button);

        // Reset after delay
        setTimeout(() => {
          button.disabled = false;
          button.querySelector('span').textContent = originalText;
          button.style.background = '';
        }, 1500);

        // Update cart badge
        updateCartBadge();
      } else {
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

  function updateCartBadge() {
    if (!window.ShoppingCart) return;
    
    const cart = window.ShoppingCart.getCart();
    const badge = document.querySelector('.cart-button__badge');
    
    if (badge) {
      const totalItems = cart.items.reduce((sum, item) => sum + item.quantity, 0);
      badge.textContent = totalItems > 0 ? totalItems : '';
      badge.style.display = totalItems > 0 ? 'flex' : 'none';
    }
  }

  // Único CTA de checkout de la página: vive en el panel sticky para seguir
  // accesible aunque el cliente agregue desde la calculadora, más abajo.
  function showCheckoutShortcut(button) {
    const container =
      (button && button.closest('.purchase-panel__actions')) ||
      document.querySelector('.purchase-panel__actions') ||
      document.querySelector('.vitola-purchase-panel');
    if (!container) return;

    let cta = document.querySelector('.purchase-panel__checkout-cta');
    if (!cta) {
      cta = document.createElement('a');
      cta.className = 'purchase-panel__button purchase-panel__button--checkout purchase-panel__checkout-cta';
      container.appendChild(cta);
    }

    cta.href = typeof getCheckoutUrl === 'function' ? getCheckoutUrl() : '/checkout.html';
    cta.textContent = 'Finalizar compra →';
    cta.hidden = false;
  }

  window.revealCheckoutShortcut = function revealCheckoutShortcut() {
    showCheckoutShortcut(null);
  };

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupPurchasePanels);
  } else {
    setupPurchasePanels();
  }

  // Listen for cart updates
  window.addEventListener('cds:cart-updated', updateCartBadge);

})();
