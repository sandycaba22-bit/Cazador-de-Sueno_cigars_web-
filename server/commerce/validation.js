/**
 * Validación y saneado de los datos que envía el comprador.
 *
 * El checkout se redujo a los campos que realmente hacen falta para que DHL
 * entregue el paquete: nombre, correo, teléfono, dirección, ciudad y país.
 * Estado y código postal dejaron de ser obligatorios porque buena parte de los
 * destinos internacionales no los usan, y cada campo obligatorio de más es
 * abandono de carrito.
 */

const { CheckoutError, ERROR_CODES } = require('./errors');
const { getCountryList } = require('../../js/shipping');

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const LIMITS = {
  fullName: 120,
  email: 160,
  phone: 40,
  address: 240,
  city: 80,
  state: 80,
  postalCode: 24,
  notes: 500,
};

/** Elimina caracteres de control que corromperían el log o el fichero JSON. */
function clean(value, maxLength) {
  return String(value ?? '')
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001F\u007F]/g, ' ')
    .trim()
    .slice(0, maxLength);
}

function isKnownCountry(code) {
  return getCountryList().some((country) => country.code === code);
}

/**
 * @param {object} raw Cuerpo recibido del navegador.
 * @returns {{ customer: object, shipping: object, notes: string, acceptances: object }}
 */
function parseCheckoutInput(raw) {
  const errors = [];

  const fullName = clean(raw?.customer?.fullName, LIMITS.fullName);
  const email = clean(raw?.customer?.email, LIMITS.email).toLowerCase();
  const phone = clean(raw?.customer?.phone, LIMITS.phone);

  const address = clean(raw?.shipping?.address, LIMITS.address);
  const city = clean(raw?.shipping?.city, LIMITS.city);
  const state = clean(raw?.shipping?.state, LIMITS.state);
  const postalCode = clean(raw?.shipping?.postalCode, LIMITS.postalCode);
  const country = clean(raw?.shipping?.country, 8).toUpperCase();

  const notes = clean(raw?.notes, LIMITS.notes);

  if (fullName.length < 3) errors.push('Escribe tu nombre completo.');
  if (!EMAIL_PATTERN.test(email)) errors.push('Escribe un correo electrónico válido.');
  if (address.length < 5) errors.push('Escribe la dirección de entrega.');
  if (city.length < 2) errors.push('Escribe la ciudad de entrega.');
  if (!country || !isKnownCountry(country)) errors.push('Selecciona el país de destino.');

  // Sin teléfono DHL no puede coordinar la entrega internacional.
  if (phone.replace(/\D/g, '').length < 7) {
    errors.push('Escribe un teléfono de contacto para la entrega.');
  }

  const acceptFinalSale = raw?.acceptances?.finalSale === true;
  const acceptCustoms = raw?.acceptances?.customs === true;
  if (!acceptFinalSale) errors.push('Debes aceptar la política de venta final.');
  if (!acceptCustoms) errors.push('Debes aceptar la responsabilidad aduanera.');

  if (errors.length) {
    throw new CheckoutError(ERROR_CODES.VALIDATION_FAILED, errors[0], {
      diagnostics: { errorCount: errors.length, errors },
    });
  }

  return {
    customer: { fullName, email, phone },
    shipping: { address, city, state, postalCode, country },
    notes,
    acceptances: { finalSale: true, customs: true, acceptedAt: new Date().toISOString() },
  };
}

module.exports = { parseCheckoutInput, clean, EMAIL_PATTERN, LIMITS };
