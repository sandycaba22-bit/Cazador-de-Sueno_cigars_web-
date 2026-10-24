const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const links = require('../../../js/bank-transfer-links');
const { APP_CONFIG } = require('../../../js/config');
const { createBankTransferGateway } = require('../gateways/bank-transfer');
const { config } = require('../config');
const root = path.join(__dirname, '../../..');
const email = 'cazadordesueno1@gmail.com';

test('contacto y comprobantes comparten el correo oficial', () => {
  assert.equal(APP_CONFIG.contact.email, email);
  assert.equal(APP_CONFIG.bankTransfer.email, email);
  assert.equal(createBankTransferGateway(APP_CONFIG).describe().client.email, email);
  if (!process.env.HOUSE_EMAIL) assert.equal(config.contact.email, email);
});

test('los enlaces oficiales reconocen los nombres de los bancos', () => {
  for (const name of ['Banco de Reservas', 'Banreservas', 'Banco Reservas']) {
    assert.equal(links.resolve(name).url, 'https://www.banreservas.com');
  }
  assert.equal(links.resolve('Banco BHD').url, 'https://www.bhd.com.do');
  assert.equal(links.resolve('BANCO BHD LEON').url, 'https://www.bhd.com.do');
});

test('los enlaces abren otra pestana con proteccion de opener y referrer', () => {
  for (const account of APP_CONFIG.bankTransfer.accounts) {
    const html = links.render(account.bankName);
    assert.ok(html.includes('target="_blank" rel="noopener noreferrer"'));
    assert.ok(html.includes('class="co-bank__link"'));
  }
});

test('no admite URL arbitraria ni HTML en el texto del enlace', () => {
  assert.equal(links.render('javascript:alert(1)'), '');
  const html = links.render('BHD', '<script>"&');
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;&quot;&amp;'));
});

test('el texto del enlace esta disponible en todos los idiomas', () => {
  for (const file of fs.readdirSync(path.join(root, 'locales'))) {
    const locale = JSON.parse(fs.readFileSync(path.join(root, 'locales', file), 'utf8'));
    assert.equal(typeof locale.translations.checkout.bank.online, 'string', file);
    assert.ok(locale.translations.checkout.bank.online.length, file);
  }
});

test('el aviso de metodo no disponible esta en todos los idiomas', () => {
  for (const file of fs.readdirSync(path.join(root, 'locales'))) {
    const locale = JSON.parse(fs.readFileSync(path.join(root, 'locales', file), 'utf8'));
    assert.equal(typeof locale.translations.checkout.unavailable, 'string', file);
    assert.ok(locale.translations.checkout.unavailable.length, file);
  }
});

test('copiar cuenta, pasos de transferencia y aviso de PayPal en pruebas existen en todos los idiomas', () => {
  for (const file of fs.readdirSync(path.join(root, 'locales'))) {
    const { checkout } = JSON.parse(fs.readFileSync(path.join(root, 'locales', file), 'utf8')).translations;
    for (const key of ['copy', 'copied', 'copy_failed', 'step_copy', 'step_transfer']) {
      assert.ok(typeof checkout.bank[key] === 'string' && checkout.bank[key].length, `${file} bank.${key}`);
    }
    assert.ok(typeof checkout.paypal_sandbox === 'string' && checkout.paypal_sandbox.length, file);
  }
});

test('el boton de copiar lleva el numero exacto y escapa el texto', () => {
  const html = links.copyButton('9605921112', 'Copiar');
  assert.ok(html.includes('data-copy="9605921112"'));
  assert.ok(html.includes('type="button"'));
  assert.equal(links.copyButton(''), '');
  assert.ok(!links.copyButton('"><script>', 'x').includes('<script>'));
});

test('las paginas de vitolas y mayoristas muestran el correo de ventas', () => {
  const pages = fs.readdirSync(path.join(root, 'vitolas'))
    .filter((name) => name.endsWith('.html'))
    .map((name) => path.join('vitolas', name))
    .concat('wholesale.html');
  for (const name of pages) {
    const html = fs.readFileSync(path.join(root, name), 'utf8');
    assert.ok(html.includes('href="mailto:' + email + '"'), name);
  }
});

test('el checkout carga el concierge despues del checkout', () => {
  const html = fs.readFileSync(path.join(root, 'checkout.html'), 'utf8');
  const checkout = html.indexOf('<script src="js/checkout.js" defer></script>');
  const assistant = html.indexOf('<script src="js/checkout-assistant.js" defer></script>');
  assert.ok(checkout > -1);
  assert.ok(assistant > checkout);
});

test('checkout y confirmacion cargan el helper y muestran el contacto oficial', () => {
  for (const name of ['checkout.html', 'order-confirmation.html']) {
    const html = fs.readFileSync(path.join(root, name), 'utf8');
    assert.ok(html.includes('href="mailto:' + email + '"'), name);
    assert.ok(html.includes('src="js/bank-transfer-links.js"'), name);
    for (const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
      if (script[1].trim()) new vm.Script(script[1], { filename: name });
    }
  }
});
