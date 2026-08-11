const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const ORDERS_FILE = path.join(DATA_DIR, 'orders.json');

function ensureDataDir() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
}

function loadOrders() {
  ensureDataDir();
  if (!fs.existsSync(ORDERS_FILE)) return {};
  try {
    return JSON.parse(fs.readFileSync(ORDERS_FILE, 'utf8'));
  } catch {
    return {};
  }
}

function saveOrders(orders) {
  ensureDataDir();
  fs.writeFileSync(ORDERS_FILE, JSON.stringify(orders, null, 2), 'utf8');
}

function validateOrderPayload(order) {
  const errors = [];
  if (!order?.reference) errors.push('Referencia de pedido requerida.');
  if (!order?.customer?.email) errors.push('Email del cliente requerido.');
  if (!Array.isArray(order?.items) || order.items.length === 0) {
    errors.push('El pedido debe incluir al menos un artículo.');
  }
  if (!order?.policy?.accepted || !order?.policy?.noRefunds) {
    errors.push('Política de venta final no aceptada.');
  }
  if (!order?.customsDisclaimer?.accepted) {
    errors.push('Descargo de responsabilidad aduanera no aceptado.');
  }
  if (!Number.isFinite(order?.total) || order.total <= 0) {
    errors.push('Total de pedido inválido.');
  }

  const maxBoxes = 10;
  const shippingBoxes = Math.floor(Number(order.shippingBoxes) || 0);
  if (shippingBoxes > maxBoxes) {
    errors.push(
      'Por normativa de envíos internacionales desde República Dominicana, el máximo permitido es 10 cajas por pedido DHL.'
    );
  }

  if (order.paymentMethod === 'bank_transfer') {
    const accounts = order.bankTransfer?.accounts || [];
    if (!accounts.length) {
      errors.push('Datos bancarios no incluidos en el pedido.');
    }
  }

  return errors;
}

function createOrder(order) {
  const errors = validateOrderPayload(order);
  if (errors.length) {
    return { success: false, errors };
  }

  const orders = loadOrders();
  if (orders[order.reference]) {
    return { success: false, errors: ['La referencia de pedido ya existe.'] };
  }

  const record = {
    ...order,
    refundEligible: false,
    status:
      order.paymentStatus === 'paid' || order.paymentStatus === 'paid_sandbox'
        ? 'confirmed'
        : 'awaiting_payment',
    registeredAt: new Date().toISOString(),
  };

  orders[order.reference] = record;
  saveOrders(orders);

  console.log(`[Order] Registrado ${order.reference} — ${record.status} — ${order.paymentMethod}`);

  return { success: true, order: record };
}

function getOrder(reference) {
  const orders = loadOrders();
  return orders[reference] || null;
}

module.exports = { createOrder, getOrder, loadOrders };
