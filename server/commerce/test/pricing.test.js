const test = require('node:test');
const assert = require('node:assert/strict');

const { buildQuote } = require('../pricing');
const { getProductById } = require('../../../js/catalog');
const { calculateShipping } = require('../../../js/shipping');
const { ERROR_CODES } = require('../errors');

function expectCheckoutError(fn, code) {
  try {
    fn();
  } catch (error) {
    assert.equal(error.code, code, `se esperaba ${code} y llegó ${error.code}`);
    return error;
  }
  assert.fail(`se esperaba un error ${code}`);
}

test('calcula el total como subtotal más flete DHL, en centavos enteros', () => {
  const quote = buildQuote({
    items: [{ productId: 'emperador', unitType: 'box', quantity: 2 }],
    country: 'US',
  });

  const product = getProductById('emperador');
  const expectedSubtotal = Math.round(product.pricePerBox * 100) * 2;
  const expectedShipping = Math.round(calculateShipping('US', 2).cost * 100);

  assert.equal(quote.subtotalCents, expectedSubtotal);
  assert.equal(quote.shippingCents, expectedShipping);
  assert.equal(quote.totalCents, expectedSubtotal + expectedShipping);
  assert.equal(Number.isInteger(quote.totalCents), true);
});

test('cuenta unidades y cajas según el empaque de cada vitola', () => {
  const estandar = buildQuote({
    items: [{ productId: 'sultan', unitType: 'box', quantity: 1 }],
    country: 'MX',
  });
  assert.equal(estandar.totalUnits, 20);
  assert.equal(estandar.shippingBoxes, 1);

  const rango = buildQuote({
    items: [{ productId: 'rango', unitType: 'box', quantity: 1 }],
    country: 'MX',
  });
  assert.equal(rango.totalUnits, 10, 'El Rango empaqueta 10 unidades por caja');
  assert.equal(rango.shippingBoxes, 1);
});

test('comprar una caja cuesta lo mismo que comprar sus puros sueltos', () => {
  const porCaja = buildQuote({
    items: [{ productId: 'emperador', unitType: 'box', quantity: 1 }],
    country: 'US',
  });
  const porUnidad = buildQuote({
    items: [{ productId: 'emperador', unitType: 'unit', quantity: 20 }],
    country: 'US',
  });

  assert.equal(porCaja.subtotalCents, porUnidad.subtotalCents);
});

test('ignora cualquier precio que venga del cliente', () => {
  const quote = buildQuote({
    items: [
      {
        productId: 'exquisito',
        unitType: 'box',
        quantity: 1,
        pricePerBox: 1,
        lineTotal: 1,
        total: 1,
      },
    ],
    country: 'US',
  });

  const product = getProductById('exquisito');
  assert.equal(quote.lines[0].unitPriceCents, Math.round(product.pricePerBox * 100));
  assert.ok(quote.totalCents > 1000, 'el total sale del catálogo, no del cuerpo de la petición');
});

test('rechaza el carrito vacío', () => {
  expectCheckoutError(() => buildQuote({ items: [], country: 'US' }), ERROR_CODES.CART_EMPTY);
  expectCheckoutError(
    () => buildQuote({ items: undefined, country: 'US' }),
    ERROR_CODES.CART_EMPTY
  );
});

test('rechaza productos que no están en el catálogo', () => {
  expectCheckoutError(
    () => buildQuote({ items: [{ productId: 'inventado', quantity: 1 }], country: 'US' }),
    ERROR_CODES.UNKNOWN_PRODUCT
  );
});

test('rechaza los identificadores del catálogo de ejemplo que ya no existen', () => {
  // Si alguien vuelve a introducirlos, el pedido debe morir aquí y no en la
  // pasarela: fueron la causa de que ninguna compra se completara.
  expectCheckoutError(
    () =>
      buildQuote({
        items: [{ productId: 'cs-classic-robusto', unitType: 'box', quantity: 1 }],
        country: 'US',
      }),
    ERROR_CODES.UNKNOWN_PRODUCT
  );
});

test('rechaza cantidades no válidas', () => {
  for (const quantity of [0, -3, 'muchas', Number.NaN, 9999]) {
    expectCheckoutError(
      () =>
        buildQuote({
          items: [{ productId: 'emperador', unitType: 'box', quantity }],
          country: 'US',
        }),
      ERROR_CODES.VALIDATION_FAILED
    );
  }
});

test('aplica el límite de 10 cajas por envío DHL', () => {
  const alLimite = buildQuote({
    items: [{ productId: 'rango', unitType: 'box', quantity: 10 }],
    country: 'US',
  });
  assert.equal(alLimite.shippingBoxes, 10);

  expectCheckoutError(
    () =>
      buildQuote({
        items: [
          { productId: 'rango', unitType: 'box', quantity: 10 },
          { productId: 'emperador', unitType: 'box', quantity: 1 },
        ],
        country: 'US',
      }),
    ERROR_CODES.DHL_BOX_LIMIT
  );
});

test('rechaza líneas duplicadas del mismo producto y formato', () => {
  expectCheckoutError(
    () =>
      buildQuote({
        items: [
          { productId: 'emperador', unitType: 'box', quantity: 1 },
          { productId: 'emperador', unitType: 'box', quantity: 1 },
        ],
        country: 'US',
      }),
    ERROR_CODES.VALIDATION_FAILED
  );
});

test('un país desconocido cae en la zona más cara, no en envío gratis', () => {
  const quote = buildQuote({
    items: [{ productId: 'emperador', unitType: 'box', quantity: 1 }],
    country: 'XX',
  });
  assert.ok(quote.shippingCents > 0);
  assert.equal(quote.shipping.zoneKey, 'OTHER');
});

test('no permite superar el stock disponible', () => {
  const product = getProductById('rango');
  expectCheckoutError(
    () =>
      buildQuote({
        items: [{ productId: 'rango', unitType: 'unit', quantity: product.stockUnits + 1 }],
        country: 'US',
      }),
    ERROR_CODES.VALIDATION_FAILED
  );
});
