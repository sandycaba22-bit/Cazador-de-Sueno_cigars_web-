const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '../../..');
const OFFICIAL = '18094645016';
const RETIRED = ['18096764090', '18095550198'];
const VITOLAS = {
  'el-emperador.html': 'emperador',
  'puro-habano.html': 'puro_habano',
  'el-exquisito.html': 'exquisito',
  'el-rango.html': 'rango',
  'ligero-007.html': 'ligero',
  'el-sultan.html': 'sultan'
};

function read(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8');
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
    if (['node_modules', '.git', 'data'].includes(entry.name)) continue;
    const rel = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(rel, out);
    else if (/\.(html|js|json|txt|md|py)$/.test(entry.name)) out.push(rel);
  }
  return out;
}

function locales() {
  return fs.readdirSync(path.join(root, 'locales')).map((file) => [
    file,
    JSON.parse(read(path.join('locales', file))).translations
  ]);
}

test('ningun archivo conserva los WhatsApp retirados', () => {
  for (const rel of walk('.')) {
    if (rel.endsWith('brand-experience.test.js')) continue;
    const text = read(rel);
    for (const number of RETIRED) assert.ok(!text.includes(number), `${rel} contiene ${number}`);
  }
});

test('los botones de WhatsApp apuntan al numero de la fabrica', () => {
  assert.ok(read('vitolas/vitola-page.js').includes(`'${OFFICIAL}'`));
  assert.ok(read('js/whatsapp-commerce.js').includes(`'${OFFICIAL}'`));
  assert.ok(read('js/checkout.js').includes(`BANK_TRANSFER_WHATSAPP = '${OFFICIAL}'`));
});

test('los archivos temporales de prueba ya no existen', () => {
  for (const name of ['cart-test.html', 'index_temp.html', 'index_server.html']) {
    assert.equal(fs.existsSync(path.join(root, name)), false, name);
  }
});

test('cada vitola muestra maridaje, sello de origen, mayoristas y aviso de edad', () => {
  for (const [file, id] of Object.entries(VITOLAS)) {
    const html = read(path.join('vitolas', file));
    const heritage = html.indexOf('class="vitola-heritage"');
    assert.ok(heritage > -1, file);
    assert.ok(heritage < html.indexOf('id="purchasePanel"'), `${file}: maridaje antes de comprar`);
    for (const slot of ['spirit', 'coffee', 'bite', 'moment']) {
      assert.ok(html.includes(`data-i18n="vitolas.brand.pairings.${id}.${slot}"`), `${file} ${slot}`);
    }
    assert.ok(html.includes('class="vitola-seal"'), file);
    assert.ok(html.includes('href="../wholesale.html" data-i18n="vitolas.brand.b2b.cta"'), file);
    assert.ok(html.includes(`href="https://wa.me/${OFFICIAL}?text=`), file);
    assert.ok(html.includes('data-i18n="vitolas.brand.legal_age"'), file);
    assert.ok(html.indexOf('class="vitola-b2b"') < html.indexOf('</main>'), file);
  }
});

test('las fichas tecnicas conservan la mezcla real de cada vitola', () => {
  const blends = {
    'el-emperador.html': ['San Andrés', 'Olor Dominicano'],
    'puro-habano.html': ['Habana', 'Yamaz'],
    'el-exquisito.html': ['San Andrés', 'Doble Capote'],
    'el-rango.html': ['San Andrés', 'Nicaragua'],
    'ligero-007.html': ['San Andrés', 'Camerún'],
    'el-sultan.html': ['San Andrés', 'Olor Dominicano']
  };
  for (const [file, parts] of Object.entries(blends)) {
    const html = read(path.join('vitolas', file));
    for (const part of parts) assert.ok(html.includes(part), `${file} ${part}`);
  }
});

test('el texto de marca de las vitolas existe en todos los idiomas', () => {
  for (const [file, t] of locales()) {
    const brand = t.vitolas.brand;
    for (const key of ['title', 'spirit', 'coffee', 'bite', 'moment']) {
      assert.ok(brand.pairing[key], `${file} pairing.${key}`);
    }
    for (const id of Object.values(VITOLAS)) {
      for (const slot of ['spirit', 'coffee', 'bite', 'moment']) {
        assert.ok(brand.pairings[id][slot], `${file} ${id}.${slot}`);
      }
    }
    for (const key of ['label', 'title', 'text', 'place']) assert.ok(brand.seal[key], `${file} seal.${key}`);
    for (const key of ['label', 'title', 'text', 'cta', 'whatsapp']) assert.ok(brand.b2b[key], `${file} b2b.${key}`);
    assert.match(brand.legal_age, /21/, file);
  }
});

test('el resumen del checkout muestra pago seguro, empaque hermetico y origen', () => {
  const html = read('checkout.html');
  const summary = html.slice(html.indexOf('class="co-summary-card"'), html.indexOf('</aside>'));
  for (const key of ['secure', 'humidity', 'origin']) {
    assert.ok(summary.includes(`data-i18n="checkout.trust.${key}_title"`), key);
    assert.ok(summary.includes(`data-i18n="checkout.trust.${key}_text"`), key);
  }
  assert.ok(summary.includes('data-i18n="checkout.trust.age"'));
  for (const [file, t] of locales()) {
    for (const key of ['secure_title', 'secure_text', 'humidity_title', 'humidity_text', 'origin_title', 'origin_text', 'age']) {
      assert.ok(t.checkout.trust[key], `${file} trust.${key}`);
    }
  }
});
