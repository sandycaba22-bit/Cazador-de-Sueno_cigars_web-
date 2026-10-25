/**
 * Idioma del portal mayorista.
 * La preferencia manual vive en localStorage. Si no hay preferencia,
 * gana el primer idioma del navegador que sea español o inglés.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root && root.document) {
    root.CDSWholesaleI18n = api;
    api.start(root.document);
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  var STORAGE_KEY = 'cds_wholesale_lang';

  var DICT = {
    es: {
      'meta.title': 'Mayoristas y Distribuidores — Cazador de Sueño Cigars SRL',
      'meta.description': 'Portal mayorista de Cazador de Sueño Cigars SRL. Puros premium de República Dominicana para exportación.',
      'lang.group': 'Idioma',
      'lang.es': '🇩🇴 Español',
      'lang.en': '🇺🇸 English',
      'brand.sub': 'Cigars SRL · República Dominicana',
      'hero.title': 'Mayoristas y Distribuidores',
      'hero.brand': 'Cazador de Sueño Cigars SRL',
      'hero.lead': 'Bienvenido a nuestro portal B2B exclusivo. En Cazador de Sueño Cigars SRL elaboramos puros premium 100% hechos a mano por maestros tabaqueros en la República Dominicana, listos para la exportación global con facilidades comerciales y RNC válido.',
      'btn.catalog': 'Descargar catálogo (PDF)',
      'btn.prices': '📊 PRECIOS PARA MAYORISTA',
      'btn.inquiry': 'Consultas de mayoristas',
      'catalog.href': 'catalogo/CazadorDeSuenos_Wholesale_ES.pdf',
      'inquiry.href': 'https://wa.me/18094645016?text=Hola,%20estoy%20interesado%20en%20oportunidades%20para%20mayoristas%20con%20Cazador%20de%20Sue%C3%B1os.',
      'sales.label': 'Correo de ventas:',
      'feature.factory.title': 'Directo de fábrica',
      'feature.factory.text': 'Hechos a mano en República Dominicana con generaciones de maestría.',
      'feature.export.title': 'Exportación global',
      'feature.export.text': 'Logística lista para envíos internacionales. RNC al día y certificaciones.',
      'feature.quality.title': 'Calidad premium',
      'feature.quality.text': 'Estricto control de calidad en cada vitola antes de su empaque.',
      'age.eyebrow': 'Bienvenido',
      'age.title': 'Acceso exclusivo',
      'age.text': 'Este sitio presenta productos de tabaco premium. Confirma que eres mayor de edad.',
      'age.accept': 'Sí, soy mayor de edad',
      'age.deny': 'No',
      'sheet.close': 'Cerrar',
      'access.title': 'Acceso a precios de mayorista',
      'access.lead': 'La lista FOB se muestra en esta sesión después de confirmar que compras al por mayor.',
      'access.company': 'Razón social',
      'access.country': 'País',
      'access.email': 'Correo',
      'access.phone': 'Teléfono',
      'access.confirm': 'Confirmo que soy comprador mayorista y mayor de edad.',
      'access.submit': 'Ver lista de precios',
      'access.error': 'Indica la razón social, el país y confirma que compras al por mayor.',
      'access.saveError': 'No se pudo guardar el acceso en este navegador.',
      'board.title': '📊 Precios para mayorista',
      'board.lead': 'USD por puro. Incluyen producción, empaque de exportación y timbre.',
      'shipping.note': 'Los precios mostrados son de fábrica (FOB). El costo de envío se cobra por separado.',
      'line.rango': 'El Rango no está en la calculadora: stock limitado.',
      'tier.chipTitleBase': 'Tier {id} · Mínimo',
      'tier.chipTitleOff': 'Tier {id} · −{pct}%',
      'tier.between': '{min} a {max} unidades',
      'tier.open': '{min} unidades o más',
      'tier.chipBase': 'Precio base de entrada.',
      'tier.chipOff': '{pct}% de descuento sobre la base.',
      'tier.colBase': 'Base',
      'tier.colOff': '−{pct}%',
      'tier.baseShort': 'precio base',
      'tier.offShort': '{pct}% de descuento',
      'product.sultan': 'El Sultán',
      'product.sultan.measure': 'Robusto 50 × 5″',
      'product.ligero': 'Ligero 007',
      'product.ligero.measure': 'Toro 58 × 5″',
      'product.habano': 'Puro Habano',
      'product.habano.measure': 'Churchill 48 × 7″',
      'product.exquisito': 'El Exquisito',
      'product.exquisito.measure': 'Gran Toro 58 × 6″',
      'product.emperador': 'El Emperador',
      'product.emperador.measure': 'Gran Toro 58 × 6″',
      'product.rango': 'El Rango',
      'product.rango.measure': 'Doble Perfecto 60 × 4½″',
      'table.vitola': 'Vitola',
      'table.measure': 'Medidas',
      'table.base': 'Precio base',
      'table.baseRange': '2,000–4,999',
      'table.msrp': 'MSRP sugerido',
      'table.volume': 'Tier por volumen',
      'table.tier2': '5,000–9,999',
      'table.tier3': '10,000+',
      'table.swipe': 'Desliza hacia los lados para ver todos los precios.',
      'order.note': 'Indica las unidades de cada vitola. El tramo sale del total del pedido. Menos de 2,000 unidades no se procesa.',
      'order.process': 'Procesar pedido',
      'order.download': 'Descargar lista (PDF)',
      'order.send': 'Enviar pedido por WhatsApp',
      'quote.below': 'Sin escala: por debajo del mínimo',
      'quote.tierBase': 'Escala {id} · precio base',
      'quote.tierOff': 'Escala {id} · −{pct}%',
      'quote.units': 'Unidades',
      'quote.total': 'Total FOB',
      'moq.alert': 'Pedido por debajo del mínimo. El MOQ de exportación es de {moq} unidades. Este pedido suma {units} ({short} por debajo) y no se puede procesar.',
      'wa.order': 'Pedido mayorista Cazador de Sueño Cigars SRL\nEmpresa: {company}\n{summary}\nUnidades: {units}\nEscala: Tier {tier}\nTotal FOB: ${total}',
      'pdf.kicker': 'CAZADOR DE SUENO CIGARS SRL',
      'pdf.title': 'Precios para mayorista · FOB',
      'pdf.sub': 'USD por puro · Republica Dominicana',
      'pdf.colVitola': 'Vitola',
      'pdf.colMeasure': 'Medidas',
      'pdf.colBase': 'Base',
      'pdf.colTier2': '5,000-9,999',
      'pdf.colTier3': '10,000+',
      'pdf.colMsrp': 'MSRP',
      'pdf.note1': 'Pedido minimo (MOQ): 2,000 unidades. Por debajo de ese volumen el pedido no se procesa.',
      'pdf.note3': 'El tramo sale del total de unidades del pedido y aplica a todas las vitolas.',
      'pdf.note4': 'Incluye produccion, empaque de exportacion y timbre.',
      'pdf.shipping': 'Precios de fabrica (FOB). El costo de envio se cobra por separado.',
      'pdf.paused': 'El Rango no esta en esta lista: stock limitado.',
      'pdf.note6': 'Cajas de exportacion: 20 puros. Consultas: cazadordesueno1@gmail.com',
      'pdf.note7': 'WhatsApp +1 809-464-5016',
      'pdf.file': 'CazadorDeSuenos_Precios_Mayorista.pdf',
    },
    en: {
      'meta.title': 'Wholesale & Distributors — Cazador de Sueño Cigars SRL',
      'meta.description': 'Wholesale portal of Cazador de Sueño Cigars SRL. Premium Dominican cigars for international export.',
      'lang.group': 'Language',
      'lang.es': '🇩🇴 Español',
      'lang.en': '🇺🇸 English',
      'brand.sub': 'Cigars SRL · Dominican Republic',
      'hero.title': 'Wholesale & Distributors',
      'hero.brand': 'Cazador de Sueño Cigars SRL',
      'hero.lead': 'Welcome to our exclusive B2B portal. At Cazador de Sueño Cigars SRL, we craft 100% handmade premium cigars by master torcedores in the Dominican Republic, fully equipped for global export with complete commercial facilities.',
      'btn.catalog': 'Download catalog (PDF)',
      'btn.prices': '📊 WHOLESALE PRICES',
      'btn.inquiry': 'Wholesale inquiries',
      'catalog.href': 'catalogo/CazadorDeSuenos_Wholesale_EN.pdf',
      'inquiry.href': 'https://wa.me/18094645016?text=Hello,%20I%27m%20interested%20in%20wholesale%20opportunities%20with%20Cazador%20de%20Sue%C3%B1os.',
      'sales.label': 'Sales email:',
      'feature.factory.title': 'Direct from factory',
      'feature.factory.text': 'Handcrafted in the Dominican Republic with generations of expertise.',
      'feature.export.title': 'Global export',
      'feature.export.text': 'Logistics ready for international shipping. Valid RNC and certifications.',
      'feature.quality.title': 'Premium quality',
      'feature.quality.text': 'Strict quality control on every single vitola before packaging.',
      'age.eyebrow': 'Welcome',
      'age.title': 'Exclusive access',
      'age.text': 'This site features premium tobacco products. Please confirm you are of legal age.',
      'age.accept': 'Yes, I am of legal age',
      'age.deny': 'No',
      'sheet.close': 'Close',
      'access.title': 'Wholesale price access',
      'access.lead': 'The FOB list is shown for this session after you confirm you are buying wholesale.',
      'access.company': 'Company name',
      'access.country': 'Country',
      'access.email': 'Email',
      'access.phone': 'Phone',
      'access.confirm': 'I confirm I am a wholesale buyer and of legal age.',
      'access.submit': 'View price list',
      'access.error': 'Enter the company name, the country, and confirm you are buying wholesale.',
      'access.saveError': 'This browser could not store the access confirmation.',
      'board.title': '📊 Wholesale prices',
      'board.lead': 'USD per cigar. Includes production, export packaging and tax stamp.',
      'shipping.note': 'Prices shown are factory prices (FOB). Shipping is charged separately.',
      'line.rango': 'El Rango is not in the calculator: limited stock.',
      'tier.chipTitleBase': 'Tier {id} · Minimum',
      'tier.chipTitleOff': 'Tier {id} · −{pct}%',
      'tier.between': '{min} to {max} cigars',
      'tier.open': '{min} cigars or more',
      'tier.chipBase': 'Entry base price.',
      'tier.chipOff': '{pct}% off the base price.',
      'tier.colBase': 'Base',
      'tier.colOff': '−{pct}%',
      'tier.baseShort': 'base price',
      'tier.offShort': '{pct}% off',
      'product.sultan': 'El Sultán',
      'product.sultan.measure': 'Robusto 50 × 5″',
      'product.ligero': 'Ligero 007',
      'product.ligero.measure': 'Toro 58 × 5″',
      'product.habano': 'Puro Habano',
      'product.habano.measure': 'Churchill 48 × 7″',
      'product.exquisito': 'The Exquisite',
      'product.exquisito.measure': 'Gran Toro 58 × 6″',
      'product.emperador': 'The Emperor',
      'product.emperador.measure': 'Gran Toro 58 × 6″',
      'product.rango': 'El Rango',
      'product.rango.measure': 'Double Perfecto 60 × 4½″',
      'table.vitola': 'Vitola',
      'table.measure': 'Size',
      'table.base': 'Base price',
      'table.baseRange': '2,000–4,999',
      'table.msrp': 'Suggested MSRP',
      'table.volume': 'Volume tier',
      'table.tier2': '5,000–9,999',
      'table.tier3': '10,000+',
      'table.swipe': 'Swipe sideways to see every price.',
      'order.note': 'Enter cigars per vitola. The tier uses the order total. Fewer than 2,000 cigars cannot be processed.',
      'order.process': 'Process order',
      'order.download': 'Download list (PDF)',
      'order.send': 'Send order on WhatsApp',
      'quote.below': 'No tier: below the minimum',
      'quote.tierBase': 'Tier {id} · base price',
      'quote.tierOff': 'Tier {id} · −{pct}%',
      'quote.units': 'Units',
      'quote.total': 'FOB total',
      'moq.alert': 'Order below the minimum. The export MOQ is {moq} cigars. This order totals {units} ({short} short) and cannot be processed.',
      'wa.order': 'Wholesale order Cazador de Sueño Cigars SRL\nCompany: {company}\n{summary}\nUnits: {units}\nTier: {tier}\nFOB total: ${total}',
      'pdf.kicker': 'CAZADOR DE SUENO CIGARS SRL',
      'pdf.title': 'Wholesale prices · FOB',
      'pdf.sub': 'USD per cigar · Dominican Republic',
      'pdf.colVitola': 'Vitola',
      'pdf.colMeasure': 'Size',
      'pdf.colBase': 'Base',
      'pdf.colTier2': '5,000-9,999',
      'pdf.colTier3': '10,000+',
      'pdf.colMsrp': 'MSRP',
      'pdf.note1': 'Minimum order (MOQ): 2,000 cigars. Orders below that volume cannot be processed.',
      'pdf.note3': 'The tier uses the order total and applies to every vitola.',
      'pdf.note4': 'Includes production, export packaging and tax stamp.',
      'pdf.shipping': 'Factory prices (FOB). Shipping is charged separately.',
      'pdf.paused': 'El Rango is not on this list: limited stock.',
      'pdf.note6': 'Export boxes: 20 cigars. Inquiries: cazadordesueno1@gmail.com',
      'pdf.note7': 'WhatsApp +1 809-464-5016',
      'pdf.file': 'CazadorDeSuenos_Wholesale_Prices.pdf',
    },
  };

  function normalize(code) {
    var value = String(code || '').toLowerCase();
    if (value.indexOf('es') === 0) return 'es';
    if (value.indexOf('en') === 0) return 'en';
    return '';
  }

  function detect() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'es' || stored === 'en') return stored;
    } catch (error) {
      /* almacenamiento no disponible */
    }
    var list = [];
    if (navigator.languages && navigator.languages.length) {
      list = Array.prototype.slice.call(navigator.languages);
    } else if (navigator.language || navigator.userLanguage) {
      list = [navigator.language || navigator.userLanguage];
    }
    for (var i = 0; i < list.length; i += 1) {
      var match = normalize(list[i]);
      if (match) return match;
    }
    return 'en';
  }

  function current() {
    return document.documentElement.lang === 'es' ? 'es' : 'en';
  }

  function t(key, vars, lang) {
    var code = lang === 'es' || lang === 'en' ? lang : current();
    var bag = DICT[code] || DICT.en;
    var text = Object.prototype.hasOwnProperty.call(bag, key) ? bag[key] : DICT.es[key];
    if (text == null) text = key;
    if (vars) {
      Object.keys(vars).forEach(function (name) {
        text = String(text).split('{' + name + '}').join(String(vars[name]));
      });
    }
    return text;
  }

  function apply(doc) {
    var root = doc || document;
    var lang = current();
    root.querySelectorAll('[data-i18n]').forEach(function (node) {
      node.textContent = t(node.getAttribute('data-i18n'));
    });
    root.querySelectorAll('[data-i18n-href]').forEach(function (node) {
      node.setAttribute('href', t(node.getAttribute('data-i18n-href')));
    });
    root.querySelectorAll('[data-i18n-aria]').forEach(function (node) {
      node.setAttribute('aria-label', t(node.getAttribute('data-i18n-aria')));
    });
    root.querySelectorAll('[data-set-lang]').forEach(function (button) {
      var selected = button.getAttribute('data-set-lang') === lang;
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    document.title = t('meta.title');
    var meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute('content', t('meta.description'));
  }

  function setLang(lang, persist) {
    if (lang !== 'es' && lang !== 'en') return;
    var root = document.documentElement;
    root.lang = lang;
    root.classList.remove('lang-es', 'lang-en');
    root.classList.add(lang === 'es' ? 'lang-es' : 'lang-en');
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, lang);
      } catch (error) {
        /* seguir en memoria aunque no se pueda guardar */
      }
    }
    apply(document);
    document.dispatchEvent(new CustomEvent('cds:wholesale-lang', { detail: { lang: lang } }));
  }

  function reveal(doc) {
    var root = (doc || document).documentElement;
    root.classList.remove('i18n-pending');
    root.classList.add('i18n-ready');
  }

  function start(doc) {
    var root = doc || document;
    root.addEventListener('click', function (event) {
      var button = event.target.closest ? event.target.closest('[data-set-lang]') : null;
      if (!button || !root.contains(button)) return;
      event.preventDefault();
      setLang(button.getAttribute('data-set-lang'), true);
    });
    try {
      apply(root);
    } finally {
      reveal(root);
    }
  }

  return {
    STORAGE_KEY: STORAGE_KEY,
    DICT: DICT,
    detect: detect,
    current: current,
    t: t,
    apply: apply,
    setLang: setLang,
    start: start,
  };
});
