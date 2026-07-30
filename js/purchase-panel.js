/**
 * CAZADOR DE SUEÑOS CIGARS - Luxury Purchase Panel
 * Handles purchase panel interactions with shopping cart and lock system
 */

(function() {
  'use strict';

  console.log('Purchase Panel Script Loading...');

  // Wait for DOM and ShoppingCart to be ready
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

  function setupPurchasePanels() {
    const purchaseButtons = document.querySelectorAll('.purchase-panel__button');
    console.log('Found purchase buttons:', purchaseButtons.length);
    
    purchaseButtons.forEach((button, index) => {
      console.log(`Button ${index}: productId=${button.dataset.productId}, quantity=${button.dataset.quantity}`);
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
    console.log('Updating buttons lock state, isLocked:', isLocked);
    
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

    console.log('Purchase click - productId:', productId, 'quantity:', quantity);

    if (!productId) {
      console.error('Product ID not found on button');
      showToast('❌ Error: Product ID no encontrado en el botón', 'error');
      return;
    }

    // Verificar bloqueo del carrito
    if (ShoppingCart.isCartLocked()) {
      console.log('Cart is locked, showing notification');
      showLockNotification(button);
      showToast('🔒 Carrito bloqueado tras pago', 'error');
      return;
    }

    // Visual feedback
    const originalText = button.querySelector('span').textContent;
    button.disabled = true;
    button.querySelector('span').textContent = 'Agregando...';

    try {
      // Add to cart
      const success = ShoppingCart.addToCart(productId, quantity);
      console.log('Add to cart result:', success);
      
      if (success) {
        // Success feedback
        button.querySelector('span').textContent = '¡Agregado!';
        button.style.background = 'linear-gradient(135deg, #2d5a3d 0%, #1a3d2a 100%)';
        
        // Show visual success notification
        showToast('✅ ¡Agregado al carrito con éxito!', 'success');
        
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
        
        // Show visual error notification
        showToast('❌ Error: No se pudo agregar al carrito', 'error');
        
        setTimeout(() => {
          button.querySelector('span').textContent = originalText;
        }, 2000);
      }

    } catch (error) {
      console.error('Error adding to cart:', error);
      button.disabled = false;
      button.querySelector('span').textContent = 'Error - Reintentar';
      
      // Show visual error notification with details
      showToast('❌ Error: ' + error.message, 'error');
      
      setTimeout(() => {
        button.querySelector('span').textContent = originalText;
      }, 2000);
    }
  }

  // Función para mostrar notificaciones visuales (toasts)
  function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'cart-toast cart-toast--' + type;
    toast.innerHTML = message;
    
    // Estilos inline para garantizar que se muestre
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
    
    // Animación CSS
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
    
    // Remover después de 3 segundos
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease-in forwards';
      setTimeout(() => {
        toast.remove();
        style.remove();
      }, 300);
    }, 3000);
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
