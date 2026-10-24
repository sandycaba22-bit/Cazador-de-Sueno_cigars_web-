const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '../../..');
const brand = 'Cazador de Sue\u00f1o Cigars SRL';

test('todas las traducciones conservan el nombre exacto de la marca', () => {
  for (const name of fs.readdirSync(path.join(root, 'locales'))) {
    if (!name.endsWith('.json')) continue;
    const { translations } = JSON.parse(fs.readFileSync(path.join(root, 'locales', name), 'utf8'));
    assert.equal(translations.age_gate.title, brand, name);
    assert.equal(translations.header.brand, brand, name);
    assert.ok(translations.footer.copy.includes(brand), name);
  }
});

test('las paginas usan el nombre exacto en titulos y no conservan variantes antiguas', () => {
  const files = fs.readdirSync(root).filter((name) => name.endsWith('.html'));
  files.push(...fs.readdirSync(path.join(root, 'vitolas')).filter((name) => name.endsWith('.html'))
    .map((name) => path.join('vitolas', name)));
  const oldName = /Cazador\s+de\s+Sue(?:\u00f1|n)os\b|Cazador\s+de\s+Sue\u00f1o\s+(?:Cigar|Sigar)\b/i;
  for (const file of files) {
    const html = fs.readFileSync(path.join(root, file), 'utf8');
    assert.equal(oldName.test(html.replace(/<[^>]+>/g, ' ')), false, file);
    const title = html.match(/<title>([^<]+)<\/title>/i)?.[1];
    if (title && /Cazador/i.test(title)) assert.ok(title.includes(brand), file);
  }
});

test('la API comparte el nombre actualizado del beneficiario y del catalogo', () => {
  const { APP_CONFIG } = require('../../../js/config');
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'config/products.json'), 'utf8'));
  assert.equal(APP_CONFIG.bankTransfer.beneficiary.name, brand);
  assert.equal(catalog.brand, brand);
});
