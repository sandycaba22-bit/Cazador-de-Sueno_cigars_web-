/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema de Checkout
 * Manejo del proceso de checkout con pago por transferencia
 */

const Checkout = (function() {
  const PAYMENT_CONFIG_PATH = '/config/payment-config.json';
  let paymentConfig = null;
  
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
  
  // Mostrar detalles bancarios
  function displayBankDetails() {
    if (!paymentConfig || !paymentConfig.payment_methods.bank_transfer) return;
    
    const bankTransfer = paymentConfig.payment_methods.bank_transfer;
    
    document.getElementById('bankName').textContent = bankTransfer.bank_name;
    document.getElementById('accountName').textContent = bankTransfer.account_name;
    document.getElementById('accountNumber').textContent = bankTransfer.account_number;
    document.getElementById('accountType').textContent = bankTransfer.account_type;
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
    
    const isValid = form.checkValidity() && paymentProof.files.length > 0;
    placeOrderBtn.disabled = !isValid;
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
      paymentProof: paymentProof.name
    };
    
    // Guardar pedido en localStorage (simulación de backend)
    const orders = JSON.parse(localStorage.getItem('cds-orders') || '[]');
    orders.push(order);
    localStorage.setItem('cds-orders', JSON.stringify(orders));
    
    // Enviar notificación al admin
    await sendAdminNotification(order);
    
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
  
  // Inicializar
  async function init() {
    // Esperar a que ShoppingCart esté listo
    if (!window.ShoppingCart) {
      setTimeout(init, 100);
      return;
    }
    
    await loadPaymentConfig();
    displayBankDetails();
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
      
      if (document.getElementById('shippingForm').checkValidity() && 
          document.getElementById('paymentProof').files.length > 0) {
        
        document.getElementById('placeOrderBtn').disabled = true;
        document.getElementById('placeOrderBtn').textContent = 'Procesando...';
        
        await createOrder();
      }
    });
    
    // Escuchar actualizaciones del carrito
    window.addEventListener('cds:cart-updated', renderOrderItems);
  }
  
  return {
    init
  };
})();

// Auto-inicialización
document.addEventListener('DOMContentLoaded', () => {
  Checkout.init();
});
