/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema de Checkout
 * Manejo del proceso de checkout con pago por transferencia
 */

const Checkout = (function() {
  const PAYMENT_CONFIG_PATH = '/config/payment-config.json';
  const BANK_ACCOUNTS_PATH = '/config/bank-accounts-config.json';
  let paymentConfig = null;
  let bankAccounts = null;
  let selectedBankAccount = null;
  
  // Cargar configuración de pago
  async function loadPaymentConfig() {
    try {
      const response = await fetch(PAYMENT_CONFIG_PATH);
      const data = await response.json();
      paymentConfig = data;
      return data;
    } catch (error) {
      console.error('Error loading payment config:', error);
      return null;
    }
  }
  
  // Cargar cuentas bancarias
  async function loadBankAccounts() {
    try {
      const response = await fetch(BANK_ACCOUNTS_PATH);
      const data = await response.json();
      bankAccounts = data.bank_accounts;
      return data;
    } catch (error) {
      console.error('Error loading bank accounts:', error);
      return null;
    }
  }
  
  // Manejar selección de cuenta bancaria
  function setupBankAccountSelection() {
    const accountCards = document.querySelectorAll('.bank-account-card');
    
    accountCards.forEach(card => {
      card.addEventListener('click', function() {
        // Remover selected de todas las tarjetas
        accountCards.forEach(c => c.classList.remove('selected'));
        
        // Agregar selected a la tarjeta clickeada
        this.classList.add('selected');
        
        // Seleccionar el radio button
        const radio = this.querySelector('.bank-account-card-radio');
        radio.checked = true;
        
        // Guardar cuenta seleccionada
        selectedBankAccount = this.getAttribute('data-account-id');
        
        validateForm();
      });
    });
  }
  
  // Mostrar detalles bancarios (obsoleto, ahora se usan tarjetas)
  function displayBankDetails() {
    // Ya no se usa, las cuentas se muestran en tarjetas
  }
  
  // Renderizar items del pedido
  function renderOrderItems() {
    const cart = ShoppingCart.getCart();
    const orderItemsContainer = document.getElementById('orderItems');
    
    if (cart.items.length === 0) {
      document.getElementById('checkoutContent').style.display = 'none';
      document.getElementById('emptyCart').style.display = 'block';
      return;
    }
    
    orderItemsContainer.innerHTML = cart.items.map(item => `
      <div class="order-summary-item">
        <div class="order-summary-item-info">
          <div class="order-summary-item-name">${item.name}</div>
          <div class="order-summary-item-quantity">Cantidad: ${item.quantity}</div>
        </div>
        <div class="order-summary-item-price">$${(item.price * item.quantity).toFixed(2)}</div>
      </div>
    `).join('');
    
    // Actualizar totales
    document.getElementById('subtotal').textContent = `$${cart.subtotal.toFixed(2)}`;
    document.getElementById('shipping').textContent = `$${cart.shipping.toFixed(2)}`;
    document.getElementById('total').textContent = `$${cart.total.toFixed(2)}`;
  }
  
  // Manejar subida de archivo
  function handleFileUpload() {
    const uploadArea = document.getElementById('paymentProofUpload');
    const fileInput = document.getElementById('paymentProof');
    const fileNameDisplay = document.getElementById('fileName');
    
    uploadArea.addEventListener('click', () => fileInput.click());
    
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.style.borderColor = '#c6a25a';
      uploadArea.style.background = 'rgba(198, 162, 90, 0.1)';
    });
    
    uploadArea.addEventListener('dragleave', () => {
      uploadArea.style.borderColor = 'rgba(198, 162, 90, 0.3)';
      uploadArea.style.background = 'transparent';
    });
    
    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.style.borderColor = 'rgba(198, 162, 90, 0.3)';
      uploadArea.style.background = 'transparent';
      
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        fileInput.files = files;
        updateFileName(files[0].name);
      }
    });
    
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        updateFileName(e.target.files[0].name);
      }
    });
  }
  
  function updateFileName(fileName) {
    document.getElementById('fileName').textContent = `Archivo seleccionado: ${fileName}`;
  }
  
  // Validar formulario
  function validateForm() {
    const form = document.getElementById('shippingForm');
    const paymentProof = document.getElementById('paymentProof');
    const placeOrderBtn = document.getElementById('placeOrderBtn');
    
    // Verificar campos obligatorios
    const requiredFields = ['firstName', 'lastName', 'email', 'phone', 'address', 'city', 'country'];
    let isValid = true;
    let firstInvalidField = null;
    
    requiredFields.forEach(fieldId => {
      const field = document.getElementById(fieldId);
      if (!field || !field.value.trim()) {
        isValid = false;
        if (!firstInvalidField) firstInvalidField = field;
        if (field) field.style.borderColor = '#ff4444';
      } else {
        isValid = false;
      }
    } else {
      if (field) field.style.borderColor = '';
    }
    });
    
    // Validar email
    const emailField = document.getElementById('email');
    if (emailField && emailField.value) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(emailField.value)) {
        isValid = false;
        emailField.style.borderColor = '#ff4444';
      }
    }
    
    // Verificar archivo de comprobante
    const hasPaymentProof = paymentProof.files.length > 0;
    if (!hasPaymentProof) {
      const uploadArea = document.getElementById('paymentProofUpload');
      if (uploadArea) {
        uploadArea.style.borderColor = '#ff4444';
      }
      isValid = false;
    } else {
      const uploadArea = document.getElementById('paymentProofUpload');
      if (uploadArea) {
        uploadArea.style.borderColor = '';
      }
    }
    
    // Verificar selección de cuenta bancaria
    if (!selectedBankAccount) {
      isValid = false;
      const accountCards = document.querySelectorAll('.bank-account-card');
      accountCards.forEach(card => {
        card.style.borderColor = '#ff4444';
      });
    } else {
      const accountCards = document.querySelectorAll('.bank-account-card');
      accountCards.forEach(card => {
        if (!card.classList.contains('selected')) {
          card.style.borderColor = '';
        }
      });
    }
    
    // Verificar que el carrito no esté vacío
    const cart = ShoppingCart.getCart();
    if (cart.items.length === 0) {
      isValid = false;
    }
    
    placeOrderBtn.disabled = !isValid;
    
    if (!isValid && firstInvalidField) {
      firstInvalidField.focus();
      showToast('❌ Por favor complete todos los campos obligatorios', 'error');
    }
    
    return isValid;
  }
  
  // Crear pedido
  async function createOrder() {
    const cart = ShoppingCart.getCart();
    const form = document.getElementById('shippingForm');
    const formData = new FormData(form);
    const paymentProof = document.getElementById('paymentProof').files[0];
    
    const order = {
      id: generateOrderId(),
      date: new Date().toISOString(),
      status: 'pending',
      items: cart.items,
      subtotal: cart.subtotal,
      shipping: cart.shipping,
      total: cart.total,
      currency: cart.currency,
      shippingInfo: {
        firstName: formData.get('firstName'),
        lastName: formData.get('lastName'),
        email: formData.get('email'),
        phone: formData.get('phone'),
        address: formData.get('address'),
        city: formData.get('city'),
        postalCode: formData.get('postalCode'),
        country: formData.get('country')
      },
      paymentMethod: 'bank_transfer',
      paymentProof: paymentProof.name,
      bankAccountId: selectedBankAccount
    };
    
    // Guardar pedido en localStorage (simulación de backend)
    const orders = JSON.parse(localStorage.getItem('cds-orders') || '[]');
    orders.push(order);
    localStorage.setItem('cds-orders', JSON.stringify(orders));
    
    // Enviar notificación al admin
    await sendAdminNotification(order);
    
    // Enviar notificación por WhatsApp
    sendWhatsAppNotification(order);
    
    // Limpiar carrito
    ShoppingCart.clearCart();
    
    // Redirigir a página de confirmación
    window.location.href = `/order-confirmation.html?orderId=${order.id}`;
  }
  
  // Generar ID de pedido
  function generateOrderId() {
    const timestamp = Date.now().toString(36).toUpperCase();
    const random = Math.random().toString(36).substring(2, 8).toUpperCase();
    return `CDS-${timestamp}-${random}`;
  }
  
  // Enviar notificación al admin
  async function sendAdminNotification(order) {
    if (!paymentConfig || !paymentConfig.admin_notification.enabled) return;
    
    const adminEmail = paymentConfig.admin_notification.email;
    const subject = `${paymentConfig.admin_notification.subject_prefix} #${order.id}`;
    
    // Simulación de envío de email (en producción, esto iría a un backend)
    console.log('Sending admin notification to:', adminEmail);
    console.log('Subject:', subject);
    console.log('Order:', order);
    
    // Aquí se integraría con un servicio de email real
    // Por ahora, guardamos en localStorage para demostración
    const notifications = JSON.parse(localStorage.getItem('cds-admin-notifications') || '[]');
    notifications.push({
      orderId: order.id,
      email: adminEmail,
      subject: subject,
      order: order,
      sent: false,
      timestamp: new Date().toISOString()
    });
    localStorage.setItem('cds-admin-notifications', JSON.stringify(notifications));
  }
  
  // Generar mensaje de WhatsApp con detalles del pedido
  function generateWhatsAppMessage(order) {
    const customer = order.shippingInfo;
    const itemsList = order.items.map(item => 
      `• ${item.name} x${item.quantity} - $${(item.price * item.quantity).toFixed(2)}`
    ).join('\n');
    
    const message = `
🚀 *NUEVO PEDIDO - CAZADOR DE SUEÑOS CIGARS*

📋 *ID del Pedido:* ${order.id}
📅 *Fecha:* ${new Date(order.date).toLocaleDateString('es-DO')}

👤 *DATOS DEL CLIENTE*
• Nombre: ${customer.firstName} ${customer.lastName}
• Email: ${customer.email}
• Teléfono: ${customer.phone || 'No proporcionado'}
• País: ${customer.country}
• Ciudad: ${customer.city}
• Dirección: ${customer.address}

📦 *PRODUCTOS*
${itemsList}

💰 *RESUMEN FINANCIERO*
• Subtotal: $${order.subtotal.toFixed(2)}
• Envío: $${order.shipping.toFixed(2)}
• TOTAL: $${order.total.toFixed(2)} USD

💳 *MÉTODO DE PAGO*
• Transferencia Bancaria
• Cuenta seleccionada: ${order.bankAccountId}
• Comprobante: ${order.paymentProof}

✅ *ESTADO: Pendiente de verificación*
    `.trim();
    
    return encodeURIComponent(message);
  }
  
  // Enviar notificación por WhatsApp
  function sendWhatsAppNotification(order) {
    if (!paymentConfig || !paymentConfig.whatsapp_notification.enabled) return;
    
    const phoneNumber = paymentConfig.whatsapp_notification.phone_number;
    const message = generateWhatsAppMessage(order);
    const whatsappUrl = `https://wa.me/${phoneNumber}?text=${message}`;
    
    // Abrir WhatsApp en nueva pestaña
    window.open(whatsappUrl, '_blank');
    
    console.log('WhatsApp notification sent for order:', order.id);
  }
  
  // Inicializar
  async function init() {
    // Esperar a que ShoppingCart esté listo
    if (!window.ShoppingCart) {
      setTimeout(init, 100);
      return;
    }
    
    await loadPaymentConfig();
    await loadBankAccounts();
    setupBankAccountSelection();
    renderOrderItems();
    handleFileUpload();
    
    // Event listeners para validación
    document.getElementById('shippingForm').addEventListener('input', validateForm);
    document.getElementById('paymentProof').addEventListener('change', validateForm);
    document.getElementById('country').addEventListener('change', (e) => {
      ShoppingCart.setShippingCountry(e.target.value);
      renderOrderItems();
    });
    
    // Event listener para submit
    document.getElementById('placeOrderBtn').addEventListener('click', async (e) => {
      e.preventDefault();
      
      if (validateForm()) {
        document.getElementById('placeOrderBtn').disabled = true;
        document.getElementById('placeOrderBtn').textContent = 'Procesando...';
        
        try {
          await createOrder();
        } catch (error) {
          console.error('Error creating order:', error);
          document.getElementById('placeOrderBtn').disabled = false;
          document.getElementById('placeOrderBtn').textContent = 'Confirmar Pedido';
          showToast('❌ Error al procesar el pedido. Por favor inténtelo nuevamente.', 'error');
        }
      }
    });
    
    // Escuchar actualizaciones del carrito
    window.addEventListener('cds:cart-updated', renderOrderItems);
  }
  
  // Sistema de notificaciones visuales (toasts)
  function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'checkout-toast checkout-toast--' + type;
    toast.innerHTML = message;
    
    toast.style.cssText = `
      position: fixed;
      top: 100px;
      right: 20px;
      background: ${type === 'success' ? 'linear-gradient(135deg, #2d5a3d 0%, #1a3d2a 100%)' : 'linear-gradient(135deg, #8B0000 0%, #A52A2A 100%)'};
      color: #f4efe2;
      padding: 1rem 1.5rem;
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      z-index: 10000;
      font-family: 'Cormorant Garamond', Georgia, serif;
      font-size: 1rem;
      font-weight: 400;
      letter-spacing: 0.05em;
      border: 1px solid ${type === 'success' ? '#4caf50' : '#FFD700'};
      animation: slideIn 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
      max-width: 350px;
      backdrop-filter: blur(10px);
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
      @keyframes slideOut {
        from {
          transform: translateX(0);
          opacity: 1;
        }
        to {
          transform: translateX(100%);
          opacity: 0;
        }
      }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.4s cubic-bezier(0.45, 0, 0.15, 1) forwards';
      setTimeout(() => {
        toast.remove();
        style.remove();
      }, 400);
    }, 4000);
  }
  
  return {
    init
  };
})();

// Auto-inicialización
document.addEventListener('DOMContentLoaded', () => {
  Checkout.init();
});
