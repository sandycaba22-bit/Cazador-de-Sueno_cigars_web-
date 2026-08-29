/**
 * El catálogo del servidor y el de las páginas de producto deben ser el mismo.
 *
 * Esta divergencia es exactamente lo que impedía completar compras: las páginas
 * de vitolas añadían al carrito productos con identificadores de
 * config/products.json ('emperador', 'rango'...) mientras el servidor calculaba
 * precios contra un catálogo de ejemplo con identificadores inventados
 * ('cs-classic-robusto'...). Ninguna referencia coincidía, así que toda
 * cotización moría con "producto no disponible" antes de llegar a la pasarela.
 *
 * Mientras existan los dos ficheros, esta prueba es la que garantiza que no
 * vuelvan a separarse.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { getCatalog, getProductById, PACKAGING } = require('../../../js/catalog');

const PRODUCTS_JSON = path.join(__dirname, '..', '..', '..', 'config', 'products.json');
const productsJson = JSON.parse(fs.readFileSync(PRODUCTS_JSON, 'utf8'));
const activos = productsJson.products.filter((p) => p.active);

test('el catálogo del servidor tiene las mismas vitolas que config/products.json', () => {
  const idsServidor = getCatalog()
    .map((p) => p.id)
    .sort();
  const idsTienda = activos.map((p) => p.id).sort();

  assert.deepEqual(
    idsServidor,
    idsTienda,
    'si estos identificadores no coinciden, ninguna compra puede completarse'
  );
});

test('cada vitola cuesta lo mismo en la tienda que en el servidor', () => {
  for (const esperado of activos) {
    const real = getProductById(esperado.id);
    assert.ok(real, `falta ${esperado.id} en js/catalog.js`);

    assert.equal(
      real.pricePerUnit,
      esperado.price_usd,
      `precio por puro distinto en ${esperado.id}`
    );
    assert.equal(
      real.pricePerBox,
      esperado.price_box_usd,
      `precio por caja distinto en ${esperado.id}`
    );
  }
});

test('el tamaño de caja coincide, o el flete DHL se calcularía mal', () => {
  for (const esperado of activos) {
    const real = getProductById(esperado.id);
    assert.equal(real.unitsPerBox, esperado.box_size, `caja distinta en ${esperado.id}`);
  }
});

test('el stock del servidor no supera el declarado en la tienda', () => {
  for (const esperado of activos) {
    const real = getProductById(esperado.id);
    assert.ok(
      real.stockUnits <= esperado.stock,
      `${esperado.id}: el servidor permitiría vender más de lo que hay`
    );
  }
});

test('los nombres coinciden, para que el cliente lea lo mismo en toda la compra', () => {
  for (const esperado of activos) {
    const real = getProductById(esperado.id);
    assert.equal(real.name, esperado.name, `nombre distinto en ${esperado.id}`);
  }
});

test('cada caja tiene un precio explícito y mayor que el del puro individual', () => {
  for (const product of getCatalog()) {
    assert.ok(product.pricePerBox > 0, `${product.id}: la caja debe tener precio`);
    assert.ok(
      product.pricePerBox > product.pricePerUnit,
      `${product.id}: la caja debe costar más que un puro suelto`
    );
  }
});

test('la imagen de cada vitola existe en el repositorio', () => {
  const raiz = path.join(__dirname, '..', '..', '..');
  for (const product of getCatalog()) {
    const archivo = path.join(raiz, product.image);
    assert.ok(
      fs.existsSync(archivo),
      `${product.id}: la imagen ${product.image} no existe y saldría rota en la tienda`
    );
  }
});

test('la imagen del catálogo y la de la tienda son la misma', () => {
  for (const esperado of activos) {
    const real = getProductById(esperado.id);
    assert.equal(real.image, esperado.image, `imagen distinta en ${esperado.id}`);
  }
});

test('solo El Rango usa la caja de 10; el resto son de 20', () => {
  for (const product of getCatalog()) {
    const esperado =
      product.line === 'rango' ? PACKAGING.RANGO_UNITS : PACKAGING.STANDARD_UNITS;
    assert.equal(product.unitsPerBox, esperado, `empaque inesperado en ${product.id}`);
  }
});
