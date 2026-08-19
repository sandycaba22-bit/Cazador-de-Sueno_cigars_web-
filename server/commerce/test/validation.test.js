const test = require('node:test');
const assert = require('node:assert/strict');

const { parseCheckoutInput } = require('../validation');
const { ERROR_CODES } = require('../errors');

function entradaValida(overrides = {}) {
  return {
    customer: { fullName: 'Ana Pérez', email: 'Ana@Ejemplo.COM', phone: '+1 809 555 1234' },
    shipping: {
      address: 'Calle El Conde 102',
      city: 'Santo Domingo',
      state: '',
      postalCode: '',
      country: 'US',
    },
    notes: '',
    acceptances: { finalSale: true, customs: true },
    ...overrides,
  };
}

function expectCheckoutError(fn) {
  try {
    fn();
  } catch (error) {
    assert.equal(error.code, ERROR_CODES.VALIDATION_FAILED);
    return error;
  }
  assert.fail('se esperaba un error de validación');
}

test('acepta un pedido sin estado ni código postal', () => {
  const parsed = parseCheckoutInput(entradaValida());
  assert.equal(parsed.shipping.state, '');
  assert.equal(parsed.shipping.postalCode, '');
  assert.equal(parsed.customer.fullName, 'Ana Pérez');
});

test('normaliza el correo a minúsculas', () => {
  assert.equal(parseCheckoutInput(entradaValida()).customer.email, 'ana@ejemplo.com');
});

test('exige nombre, correo, dirección, ciudad, país y teléfono', () => {
  const casos = [
    { customer: { fullName: 'A', email: 'ana@ejemplo.com', phone: '8095551234' } },
    { customer: { fullName: 'Ana Pérez', email: 'no-es-un-correo', phone: '8095551234' } },
    { customer: { fullName: 'Ana Pérez', email: 'ana@ejemplo.com', phone: '12' } },
    { shipping: { address: '', city: 'SD', country: 'US' } },
    { shipping: { address: 'Calle 1', city: '', country: 'US' } },
    { shipping: { address: 'Calle 1', city: 'SD', country: '' } },
  ];

  for (const override of casos) {
    expectCheckoutError(() => parseCheckoutInput(entradaValida(override)));
  }
});

test('rechaza países que no están en la lista de destinos', () => {
  expectCheckoutError(() =>
    parseCheckoutInput(entradaValida({ shipping: { address: 'Calle 1', city: 'SD', country: 'ZZ' } }))
  );
});

test('exige aceptar venta final y responsabilidad aduanera', () => {
  expectCheckoutError(() =>
    parseCheckoutInput(entradaValida({ acceptances: { finalSale: false, customs: true } }))
  );
  expectCheckoutError(() =>
    parseCheckoutInput(entradaValida({ acceptances: { finalSale: true, customs: false } }))
  );
  expectCheckoutError(() => parseCheckoutInput(entradaValida({ acceptances: {} })));
});

test('no acepta una aceptación "truthy" que no sea exactamente true', () => {
  expectCheckoutError(() =>
    parseCheckoutInput(entradaValida({ acceptances: { finalSale: 'si', customs: 1 } }))
  );
});

test('elimina caracteres de control que romperían el log o el fichero JSON', () => {
  const parsed = parseCheckoutInput(
    entradaValida({
      customer: {
        fullName: 'Ana\u0000\nPérez',
        email: 'ana@ejemplo.com',
        phone: '8095551234',
      },
    })
  );
  assert.doesNotMatch(parsed.customer.fullName, /[\u0000\n]/);
});

test('recorta los campos excesivamente largos en lugar de fallar', () => {
  const parsed = parseCheckoutInput(
    entradaValida({ notes: 'x'.repeat(5000) })
  );
  assert.equal(parsed.notes.length, 500);
});

test('registra la marca de tiempo de la aceptación', () => {
  const parsed = parseCheckoutInput(entradaValida());
  assert.ok(Date.parse(parsed.acceptances.acceptedAt));
  assert.equal(parsed.acceptances.finalSale, true);
});
