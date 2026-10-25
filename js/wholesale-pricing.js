/**
 * Lista FOB y escalas de volumen del portal mayorista.
 *
 * Referencia de exportación (casas dominicanas de volumen, estilo La Aurora
 * o Davidoff): el FOB de distribuidor suele acercarse a la mitad del PVP,
 * pero con mínimos muy por encima de 2,000 puros, así el flete interno,
 * el empaque y el timbre se diluyen.
 *
 * Aquí el pedido de entrada empieza en 2,000 unidades. Para no dejar el
 * margen por debajo de producción + empaque + timbre + flete hasta el punto
 * FOB, la base (tier 1) es el 62% del precio de caja publicado dividido
 * entre los puros de esa caja. No se usa el puro suelto de la tienda:
 * El Sultán sale más caro en caja que suelto, y el mayorista recibe empaque.
 *
 * Tier 2 (5,000–9,999): −6% sobre esa base.
 * Tier 3 (10,000+): −10% sobre esa base (queda ~56% del PVP de caja).
 * El descuento sale del total de unidades del pedido, no de cada vitola.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root && root.document) {
    root.CDSWholesalePricing = api;
    var boot = function () {
      if (root.document.documentElement.dataset.wholesaleMounted === '1') return;
      api.mount(root.document);
      root.document.documentElement.dataset.wholesaleMounted = '1';
    };
    if (root.document.readyState === 'loading') {
      root.document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  var MOQ = 2000;
  var TIER_2_MIN = 5000;
  var TIER_3_MIN = 10000;
  var ENTRY_RATIO = 0.62;
  var TIER_2_OFF = 0.06;
  var TIER_3_OFF = 0.1;
  var ACCESS_KEY = 'cds_wholesale_access';
  var WHATSAPP = '18094645016';

  var SPECS = [
    {
      id: 'sultan',
      name: 'El Sultán',
      nameEn: 'El Sultán',
      format: 'Robusto 50×5',
      fallbackBox: 148,
      unitsPerBox: 20,
    },
    {
      id: 'ligero',
      name: 'Ligero 007',
      nameEn: 'Ligero 007',
      format: 'Toro 58×5',
      fallbackBox: 220,
      unitsPerBox: 20,
    },
    {
      id: 'emperador',
      name: 'El Emperador',
      nameEn: 'The Emperor',
      format: 'Gran Toro 58×6',
      fallbackBox: 240,
      unitsPerBox: 20,
    },
    {
      id: 'puro-habano',
      name: 'Puro Habano',
      nameEn: 'Puro Habano',
      format: 'Churchill 48×7',
      fallbackBox: 280,
      unitsPerBox: 20,
    },
  ];

  function money(value) {
    return Math.round(value * 100 + 1e-8) / 100;
  }

  function findRetail(id) {
    if (typeof getProductById === 'function') {
      return getProductById(id);
    }
    if (typeof require === 'function') {
      try {
        return require('./catalog.js').getProductById(id);
      } catch (error) {
        return null;
      }
    }
    return null;
  }

  function buildProducts() {
    return SPECS.map(function (spec) {
      var retail = findRetail(spec.id);
      var box = retail && typeof retail.pricePerBox === 'number' ? retail.pricePerBox : spec.fallbackBox;
      var units = retail && retail.unitsPerBox ? retail.unitsPerBox : spec.unitsPerBox;
      var base = money((box / units) * ENTRY_RATIO);
      return {
        id: spec.id,
        name: spec.name,
        nameEn: spec.nameEn,
        format: spec.format,
        unitsPerBox: units,
        packagedRetail: money(box / units),
        base: base,
        tier2: money(base * (1 - TIER_2_OFF)),
        tier3: money(base * (1 - TIER_3_OFF)),
      };
    });
  }

  function tierForUnits(units) {
    var total = Math.floor(Number(units) || 0);
    if (total < MOQ) {
      return { id: 0, discount: 0, eligible: false, min: MOQ, max: MOQ - 1 };
    }
    if (total >= TIER_3_MIN) {
      return { id: 3, discount: TIER_3_OFF, eligible: true, min: TIER_3_MIN, max: null };
    }
    if (total >= TIER_2_MIN) {
      return { id: 2, discount: TIER_2_OFF, eligible: true, min: TIER_2_MIN, max: TIER_3_MIN - 1 };
    }
    return { id: 1, discount: 0, eligible: true, min: MOQ, max: TIER_2_MIN - 1 };
  }

  function priceForTier(product, tierId) {
    if (tierId === 2) return product.tier2;
    if (tierId === 3) return product.tier3;
    return product.base;
  }

  function quoteOrder(quantities) {
    var products = buildProducts();
    var units = 0;
    var lines = products.map(function (product) {
      var raw = quantities && quantities[product.id];
      var qty = Math.floor(Number(raw));
      if (!Number.isFinite(qty) || qty < 0) qty = 0;
      units += qty;
      return { product: product, qty: qty };
    });
    var tier = tierForUnits(units);
    var totalCents = 0;
    lines.forEach(function (line) {
      line.unit = priceForTier(line.product, tier.eligible ? tier.id : 1);
      line.total = money(line.unit * line.qty);
      totalCents += Math.round(line.total * 100 + 1e-8);
    });
    return {
      units: units,
      tier: tier,
      lines: lines,
      total: totalCents / 100,
      belowMoq: units < MOQ,
      shortfall: Math.max(0, MOQ - units),
      moq: MOQ,
    };
  }

  function formatUsd(amount, lang) {
    return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-DO', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  }

  function formatInt(amount, lang) {
    return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-DO').format(amount);
  }

  function readAccess() {
    try {
      var raw = sessionStorage.getItem(ACCESS_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || typeof data.company !== 'string' || data.company.trim().length < 2) return null;
      return data;
    } catch (error) {
      return null;
    }
  }

  function ageAccepted() {
    return document.cookie.indexOf('cds_age_gate=accepted') !== -1;
  }

  var WINANS = {
    á: '\\341', é: '\\351', í: '\\355', ó: '\\363', ú: '\\372',
    Á: '\\301', É: '\\311', Í: '\\315', Ó: '\\323', Ú: '\\332',
    ñ: '\\361', Ñ: '\\321', ü: '\\374', '¿': '\\277', '¡': '\\241',
    '×': 'x', '—': '-', '–': '-',
  };

  function pdfText(value) {
    var out = '';
    var source = String(value);
    for (var i = 0; i < source.length; i += 1) {
      var ch = source.charAt(i);
      if (WINANS[ch]) out += WINANS[ch];
      else if (ch === '\\' || ch === '(' || ch === ')') out += '\\' + ch;
      else if (ch.charCodeAt(0) < 32 || ch.charCodeAt(0) > 126) out += '?';
      else out += ch;
    }
    return out;
  }

  function pdfLine(x, y, size, rgb, text) {
    return rgb + ' rg BT /F1 ' + size + ' Tf 1 0 0 1 ' + x + ' ' + y + ' Tm (' + pdfText(text) + ') Tj ET\n';
  }

  function buildPricePdf(lang) {
    var products = buildProducts();
    var code = lang === 'en' ? 'en' : 'es';
    var ops = '';
    ops += '0.05 0.07 0.12 rg 0 748 595 94 re f\n';
    ops += '0.77 0.64 0.35 rg 48 748 499 1.2 re f\n';
    ops += pdfLine(48, 802, 11, '0.77 0.64 0.35', tr('pdf.kicker', null, code));
    ops += pdfLine(48, 776, 16, '1 1 1', tr('pdf.title', null, code));
    ops += pdfLine(48, 758, 9, '0.85 0.8 0.7', tr('pdf.sub', null, code));

    var headers = [
      tr('pdf.colVitola', null, code),
      tr('pdf.colFormat', null, code),
      '2,000-4,999',
      '5,000-9,999',
      '10,000+',
    ];
    var cols = [48, 168, 300, 400, 498];
    var y = 710;
    headers.forEach(function (label, index) {
      ops += pdfLine(cols[index], y, 9, '0.45 0.34 0.16', label);
    });
    ops += '0.77 0.64 0.35 RG 48 ' + (y - 6) + ' m 547 ' + (y - 6) + ' l S\n';

    products.forEach(function (product, index) {
      var rowY = 678 - index * 36;
      var ink = '0.12 0.1 0.08';
      ops += pdfLine(cols[0], rowY, 11, ink, code === 'en' ? product.nameEn : product.name);
      ops += pdfLine(cols[1], rowY, 10, ink, product.format);
      ops += pdfLine(cols[2], rowY, 11, ink, '$' + product.base.toFixed(2));
      ops += pdfLine(cols[3], rowY, 11, ink, '$' + product.tier2.toFixed(2));
      ops += pdfLine(cols[4], rowY, 11, ink, '$' + product.tier3.toFixed(2));
      ops += '0.8 0.76 0.7 RG 48 ' + (rowY - 10) + ' m 547 ' + (rowY - 10) + ' l S\n';
    });

    var notes = ['pdf.note1', 'pdf.note2', 'pdf.note3', 'pdf.note4', 'pdf.note5', 'pdf.note6', 'pdf.note7'].map(function (key) {
      return tr(key, null, code);
    });
    notes.forEach(function (line, index) {
      ops += pdfLine(48, 500 - index * 18, 10, '0.2 0.16 0.12', line);
    });

    var objects = [
      '<< /Type /Catalog /Pages 2 0 R >>',
      '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
      '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
      '<< /Length ' + ops.length + ' >>\nstream\n' + ops + 'endstream',
      '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ];

    var header = '%PDF-1.4\n';
    var body = '';
    var offsets = [0];
    objects.forEach(function (part, index) {
      offsets.push(header.length + body.length);
      body += String(index + 1) + ' 0 obj\n' + part + '\nendobj\n';
    });
    var xrefAt = header.length + body.length;
    var xref = 'xref\n0 ' + (objects.length + 1) + '\n0000000000 65535 f \n';
    for (var i = 1; i < offsets.length; i += 1) {
      xref += String(offsets[i]).padStart(10, '0') + ' 00000 n \n';
    }
    var trailer =
      'trailer\n<< /Size ' + (objects.length + 1) + ' /Root 1 0 R >>\nstartxref\n' + xrefAt + '\n%%EOF';
    var source = header + body + xref + trailer;
    var bytes = new Uint8Array(source.length);
    for (var c = 0; c < source.length; c += 1) bytes[c] = source.charCodeAt(c) & 255;
    return bytes;
  }

  function tr(key, vars, lang) {
    var i18n = typeof CDSWholesaleI18n !== 'undefined' ? CDSWholesaleI18n : null;
    if (i18n && typeof i18n.t === 'function') return i18n.t(key, vars, lang);
    return key;
  }

  function downloadPricePdf(lang) {
    var bytes = buildPricePdf(lang);
    var blob = new Blob([bytes], { type: 'application/pdf' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = tr('pdf.file', null, lang);
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1500);
  }

  function langOf(doc) {
    if (typeof CDSWholesaleI18n !== 'undefined' && typeof CDSWholesaleI18n.current === 'function') {
      return CDSWholesaleI18n.current();
    }
    return doc.documentElement.lang === 'en' ? 'en' : 'es';
  }

  function mount(doc) {
    var sheet = doc.getElementById('wholesale-sheet');
    var accessPanel = doc.querySelector('[data-wholesale-access]');
    var board = doc.querySelector('[data-wholesale-board]');
    if (!sheet || !accessPanel || !board) return;

    var accessForm = doc.getElementById('wholesale-access-form');
    var accessError = doc.getElementById('wholesale-access-error');
    var orderForm = doc.getElementById('wholesale-order-form');
    var moqAlert = doc.getElementById('wholesale-moq-alert');
    var quoteBox = doc.getElementById('wholesale-quote');
    var send = doc.getElementById('wholesale-send');
    var panel = sheet.querySelector('.b2b-sheet__panel');
    var lastFocus = null;
    var lastQuote = null;

    function orderMessage(quote, lang) {
      var access = readAccess();
      var summary = quote.lines
        .filter(function (line) { return line.qty > 0; })
        .map(function (line) {
          return productName(line.product, lang) + ': ' + line.qty + ' x $' + line.unit.toFixed(2);
        })
        .join('\n');
      return tr('wa.order', {
        company: access ? access.company : '',
        summary: summary,
        units: quote.units,
        tier: quote.tier.id,
        total: quote.total.toFixed(2),
      }, lang);
    }

    function resetSend() {
      send.hidden = true;
      send.removeAttribute('href');
    }

    function productName(product, lang) {
      return lang === 'en' ? product.nameEn : product.name;
    }

    function renderTable() {
      var lang = langOf(doc);
      var products = buildProducts();
      products.forEach(function (product) {
        var row = doc.querySelector('[data-wholesale-row="' + product.id + '"]');
        if (!row) return;
        var nameCell = row.querySelector('[data-col="name"]');
        var formatCell = row.querySelector('[data-col="format"]');
        if (nameCell) nameCell.textContent = productName(product, lang);
        if (formatCell) formatCell.textContent = product.format;
        row.querySelector('[data-col="tier1"]').textContent = formatUsd(product.base, lang);
        row.querySelector('[data-col="tier2"]').textContent = formatUsd(product.tier2, lang);
        row.querySelector('[data-col="tier3"]').textContent = formatUsd(product.tier3, lang);
      });
    }

    function readQuantities() {
      var quantities = {};
      SPECS.forEach(function (spec) {
        var input = orderForm.querySelector('[data-qty="' + spec.id + '"]');
        quantities[spec.id] = input ? input.value : 0;
      });
      return quantities;
    }

    function clearTierHighlight() {
      doc.querySelectorAll('[data-tier-chip], [data-tier-col]').forEach(function (node) {
        node.classList.remove('is-active');
      });
    }

    function showQuote(quote, lang) {
      lastQuote = quote;
      clearTierHighlight();
      if (!quote.belowMoq) {
        doc.querySelectorAll('[data-tier-chip="' + quote.tier.id + '"], [data-tier-col="' + quote.tier.id + '"]').forEach(function (node) {
          node.classList.add('is-active');
        });
      }
      var lines = quote.lines
        .filter(function (line) { return line.qty > 0; })
        .map(function (line) {
          return productName(line.product, lang) + ': ' + formatInt(line.qty, lang) + ' × ' + formatUsd(line.unit, lang);
        });
      var tierLabel = quote.belowMoq
        ? tr('quote.below', null, lang)
        : quote.tier.discount
          ? tr('quote.tierOff', { id: quote.tier.id, pct: Math.round(quote.tier.discount * 100) }, lang)
          : tr('quote.tierBase', { id: quote.tier.id }, lang);
      quoteBox.hidden = false;
      quoteBox.innerHTML =
        '<strong>' + tierLabel + '</strong>' +
        '<span>' + tr('quote.units', null, lang) + ': ' + formatInt(quote.units, lang) + '</span>' +
        (lines.length ? '<span>' + lines.join(' · ') + '</span>' : '') +
        '<span>' + tr('quote.total', null, lang) + ': ' + formatUsd(quote.total, lang) + '</span>';
    }

    function hideAlert() {
      moqAlert.hidden = true;
      moqAlert.textContent = '';
      orderForm.classList.remove('is-moq-blocked');
      orderForm.removeAttribute('aria-invalid');
    }

    function showMoqAlert(quote, lang) {
      moqAlert.hidden = false;
      orderForm.classList.add('is-moq-blocked');
      orderForm.setAttribute('aria-invalid', 'true');
      moqAlert.textContent = tr('moq.alert', {
        moq: formatInt(MOQ, lang),
        units: formatInt(quote.units, lang),
        short: formatInt(quote.shortfall, lang),
      }, lang);
      moqAlert.scrollIntoView({ block: 'nearest' });
    }

    function openSheet(opener) {
      if (!ageAccepted()) return;
      lastFocus = opener || doc.activeElement;
      renderTable();
      var access = readAccess();
      accessPanel.hidden = !!access;
      board.hidden = !access;
      panel.setAttribute('aria-labelledby', access ? 'wholesale-board-title' : 'wholesale-sheet-title');
      sheet.hidden = false;
      doc.body.style.overflow = 'hidden';
      var focusTarget = access ? doc.getElementById('wholesale-download') : doc.getElementById('wholesale-company');
      if (focusTarget) focusTarget.focus();
    }

    function closeSheet() {
      sheet.hidden = true;
      doc.body.style.overflow = '';
      if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
    }

    doc.querySelectorAll('[data-wholesale-prices]').forEach(function (button) {
      button.addEventListener('click', function () {
        openSheet(button);
      });
    });

    doc.querySelectorAll('[data-sheet-close]').forEach(function (node) {
      node.addEventListener('click', closeSheet);
    });

    doc.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !sheet.hidden) closeSheet();
    });

    accessForm.addEventListener('submit', function (event) {
      event.preventDefault();
      var lang = langOf(doc);
      var company = doc.getElementById('wholesale-company').value.trim();
      var country = doc.getElementById('wholesale-country').value.trim();
      var confirmed = doc.getElementById('wholesale-confirm').checked;
      if (company.length < 2 || country.length < 2 || !confirmed) {
        accessError.hidden = false;
        accessError.textContent = tr('access.error', null, lang);
        return;
      }
      accessError.hidden = true;
      try {
        sessionStorage.setItem(ACCESS_KEY, JSON.stringify({
          company: company,
          country: country,
          at: Date.now(),
        }));
      } catch (error) {
        accessError.hidden = false;
        accessError.textContent = tr('access.saveError', null, lang);
        return;
      }
      accessPanel.hidden = true;
      board.hidden = false;
      panel.setAttribute('aria-labelledby', 'wholesale-board-title');
      renderTable();
      doc.getElementById('wholesale-download').focus();
    });

    orderForm.addEventListener('input', function () {
      hideAlert();
      resetSend();
      var lang = langOf(doc);
      var quote = quoteOrder(readQuantities());
      if (quote.units > 0) showQuote(quote, lang);
      else {
        lastQuote = null;
        quoteBox.hidden = true;
        clearTierHighlight();
      }
    });

    orderForm.addEventListener('submit', function (event) {
      event.preventDefault();
      var lang = langOf(doc);
      var quote = quoteOrder(readQuantities());
      showQuote(quote, lang);
      if (quote.belowMoq) {
        resetSend();
        showMoqAlert(quote, lang);
        return;
      }
      hideAlert();
      var message = orderMessage(quote, lang);
      send.hidden = false;
      send.href = 'https://wa.me/' + WHATSAPP + '?text=' + encodeURIComponent(message);
      send.focus();
    });

    doc.getElementById('wholesale-download').addEventListener('click', function () {
      if (!readAccess()) {
        accessPanel.hidden = false;
        board.hidden = true;
        return;
      }
      downloadPricePdf(langOf(doc));
    });

    doc.addEventListener('cds:wholesale-lang', function () {
      renderTable();
      if (!lastQuote || !lastQuote.units) return;
      var lang = langOf(doc);
      showQuote(lastQuote, lang);
      if (!moqAlert.hidden) showMoqAlert(lastQuote, lang);
      if (!send.hidden && !lastQuote.belowMoq) {
        send.href = 'https://wa.me/' + WHATSAPP + '?text=' + encodeURIComponent(orderMessage(lastQuote, lang));
      }
    });
  }

  return {
    MOQ: MOQ,
    TIER_2_MIN: TIER_2_MIN,
    TIER_3_MIN: TIER_3_MIN,
    ENTRY_RATIO: ENTRY_RATIO,
    buildProducts: buildProducts,
    tierForUnits: tierForUnits,
    quoteOrder: quoteOrder,
    buildPricePdf: buildPricePdf,
    mount: mount,
  };
});
