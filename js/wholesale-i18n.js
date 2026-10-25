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
      'access.confirm': 'Confirmo que soy comprador mayorista y mayor de edad.',
      'access.submit': 'Ver lista de precios',
      'access.error': 'Indica la razón social, el país y confirma que compras al por mayor.',
      'access.saveError': 'No se pudo guardar el acceso en este navegador.',
      'board.title': '📊 Precios para mayorista',
      'board.lead': 'USD por puro, FOB República Dominicana. Incluyen producción, empaque de exportación y timbre. El flete internacional y los aranceles del destino se cotizan aparte.',
      'tier1.title': 'Tier 1 · Mínimo',
      'tier1.text': '2,000 a 4,999 unidades. Precio base de entrada.',
      'tier2.title': 'Tier 2 · −6%',
      'tier2.text': '5,000 a 9,999 unidades. 6% de descuento sobre la base.',
      'tier3.title': 'Tier 3 · −10%',
      'tier3.text': '10,000 unidades o más. 10% de descuento sobre la base.',
      'table.vitola': 'Vitola',
      'table.format': 'Formato',
      'table.base': 'Base',
      'order.note': 'Indica las unidades de cada vitola. El descuento sale del total del pedido. Menos de 2,000 unidades no se procesa.',
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
      'pdf.colFormat': 'Formato',
      'pdf.note1': 'Pedido minimo (MOQ): 2,000 unidades. Por debajo de ese volumen el pedido no se procesa.',
      'pdf.note2': 'De 2,000 a 4,999: precio base. De 5,000 a 9,999: 6% de descuento. Desde 10,000: 10%.',
      'pdf.note3': 'El descuento se calcula sobre el total de unidades del pedido y aplica a todas las vitolas.',
      'pdf.note4': 'FOB Republica Dominicana. Incluye produccion, empaque de exportacion y timbre.',
      'pdf.note5': 'El flete internacional y los aranceles del destino se cotizan aparte.',
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
      'access.confirm': 'I confirm I am a wholesale buyer and of legal age.',
      'access.submit': 'View price list',
      'access.error': 'Enter the company name, the country, and confirm you are buying wholesale.',
      'access.saveError': 'This browser could not store the access confirmation.',
      'board.title': '📊 Wholesale prices',
      'board.lead': 'USD per cigar, FOB Dominican Republic. Includes production, export packaging and tax stamp. International freight and destination duties are quoted separately.',
      'tier1.title': 'Tier 1 · Minimum',
      'tier1.text': '2,000 to 4,999 cigars. Entry base price.',
      'tier2.title': 'Tier 2 · −6%',
      'tier2.text': '5,000 to 9,999 cigars. 6% off the base price.',
      'tier3.title': 'Tier 3 · −10%',
      'tier3.text': '10,000 cigars or more. 10% off the base price.',
      'table.vitola': 'Vitola',
      'table.format': 'Format',
      'table.base': 'Base',
      'order.note': 'Enter cigars per vitola. The discount uses the order total. Fewer than 2,000 cigars cannot be processed.',
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
      'pdf.colFormat': 'Format',
      'pdf.note1': 'Minimum order (MOQ): 2,000 cigars. Orders below that volume cannot be processed.',
      'pdf.note2': '2,000 to 4,999: base price. 5,000 to 9,999: 6% off. 10,000 and above: 10% off.',
      'pdf.note3': 'The discount is based on total cigars in the order and applies to every vitola.',
      'pdf.note4': 'FOB Dominican Republic. Includes production, export packaging and tax stamp.',
      'pdf.note5': 'International freight and destination duties are quoted separately.',
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
