/**
 * Cazador de Sueños — Sommelier de Cava
 * Widget flotante con streaming hacia /api/ai-sommelier
 */
(function () {
  'use strict';

  const API_URL = '/api/ai-sommelier';
  const STORAGE_KEY = 'cds-sommelier-open';
  const MAX_TURNS = 16;

  const I18N = {
    es: {
      fab: 'Sommelier de Cava — Asesor de la casa',
      kicker: 'Cazador de Sueños',
      title: 'Sommelier de Cava',
      welcome: 'Bienvenido a la cava. Soy el maestro tabaquero de la casa. ¿Busca una recomendación de vitola, notas de cata, o representa a un distribuidor?',
      placeholder: 'Escriba su consulta…',
      send: 'Enviar',
      close: 'Cerrar',
      error: 'La cava está en silencio por un momento. Intente de nuevo.',
      recommend: 'Recomiéndeme una vitola',
      b2b: 'Soy importador / distribuidor',
      tasting: 'Notas de El Emperador',
      whatsapp: 'Continuar por WhatsApp con la casa',
      disclaimer: 'Solo para mayores de 21 años · Tabaco premium'
    },
    en: {
      fab: 'Cellar Sommelier — House advisor',
      kicker: 'Cazador de Sueños',
      title: 'Cellar Sommelier',
      welcome: 'Welcome to the cellar. I am the house master blender. Are you looking for a vitola recommendation, tasting notes, or do you represent a distributor?',
      placeholder: 'Write your inquiry…',
      send: 'Send',
      close: 'Close',
      error: 'The cellar is quiet for a moment. Please try again.',
      recommend: 'Recommend a vitola',
      b2b: 'I am an importer / distributor',
      tasting: 'Notes on El Emperador',
      whatsapp: 'Continue on WhatsApp with the house',
      disclaimer: 'Adults 21+ only · Premium tobacco'
    },
    fr: {
      fab: 'Sommelier de cave — Conseiller de la maison',
      kicker: 'Cazador de Sueños',
      title: 'Sommelier de cave',
      welcome: 'Bienvenue dans la cave. Je suis le maître torcedor de la maison. Cherchez-vous une recommandation de vitola, des notes de dégustation, ou représentez-vous un distributeur ?',
      placeholder: 'Écrivez votre demande…',
      send: 'Envoyer',
      close: 'Fermer',
      error: 'La cave est silencieuse un instant. Veuillez réessayer.',
      recommend: 'Recommandez-moi une vitola',
      b2b: 'Je suis importateur / distributeur',
      tasting: 'Notes de El Emperador',
      whatsapp: 'Continuer sur WhatsApp avec la maison',
      disclaimer: 'Réservé aux 21 ans et plus · Tabac premium'
    },
    de: {
      fab: 'Keller-Sommelier — Berater des Hauses',
      kicker: 'Cazador de Sueños',
      title: 'Keller-Sommelier',
      welcome: 'Willkommen im Keller. Ich bin der Meisterblender des Hauses. Suchen Sie eine Vitola-Empfehlung, Verkostungsnotizen, oder vertreten Sie einen Distributor?',
      placeholder: 'Schreiben Sie Ihre Anfrage…',
      send: 'Senden',
      close: 'Schließen',
      error: 'Der Keller ist einen Moment still. Bitte versuchen Sie es erneut.',
      recommend: 'Empfehlen Sie eine Vitola',
      b2b: 'Ich bin Importeur / Distributor',
      tasting: 'Noten von El Emperador',
      whatsapp: 'Auf WhatsApp mit dem Haus fortfahren',
      disclaimer: 'Nur für Personen ab 21 Jahren · Premium-Tabak'
    },
    ar: {
      fab: 'خبير القبو — مستشار الدار',
      kicker: 'Cazador de Sueños',
      title: 'خبير القبو',
      welcome: 'أهلاً بك في القبو. أنا معلّم التبغ في الدار. هل تبحث عن توصية بفيتولا، أو ملاحظات تذوق، أم تمثل موزّعاً؟',
      placeholder: 'اكتب استفسارك…',
      send: 'إرسال',
      close: 'إغلاق',
      error: 'القبو صامت للحظة. حاول مرة أخرى.',
      recommend: 'أوصني بفيتولا',
      b2b: 'أنا مستورد / موزّع',
      tasting: 'نوتات إل إمبيرادور',
      whatsapp: 'المتابعة عبر واتساب مع الدار',
      disclaimer: 'لمن تجاوز 21 عاماً · تبغ فاخر'
    },
    ru: {
      fab: 'Сомелье погреба — советник дома',
      kicker: 'Cazador de Sueños',
      title: 'Сомелье погреба',
      welcome: 'Добро пожаловать в погреб. Я мастер-блендер дома. Вам нужна рекомендация витолы, дегустационные ноты или вы представляете дистрибьютора?',
      placeholder: 'Напишите ваш запрос…',
      send: 'Отправить',
      close: 'Закрыть',
      error: 'Погреб на мгновение затих. Попробуйте ещё раз.',
      recommend: 'Порекомендуйте витолу',
      b2b: 'Я импортёр / дистрибьютор',
      tasting: 'Ноты El Emperador',
      whatsapp: 'Продолжить в WhatsApp с домом',
      disclaimer: 'Только 21+ · Премиальный табак'
    },
    zh: {
      fab: '酒窖侍酒师 — 品牌顾问',
      kicker: 'Cazador de Sueños',
      title: '酒窖侍酒师',
      welcome: '欢迎来到酒窖。我是本宅的调配大师。您是在寻找维托拉推荐、品鉴笔记，还是代表经销商？',
      placeholder: '请写下您的咨询…',
      send: '发送',
      close: '关闭',
      error: '酒窖暂时安静。请稍后再试。',
      recommend: '请为我推荐一支维托拉',
      b2b: '我是进口商 / 经销商',
      tasting: '皇帝的品鉴笔记',
      whatsapp: '通过 WhatsApp 与本宅继续',
      disclaimer: '仅限 21 岁以上 · 精品烟草'
    }
  };

  function currentLang() {
    if (window.LanguageSwitcher && typeof window.LanguageSwitcher.getCurrentLanguage === 'function') {
      return window.LanguageSwitcher.getCurrentLanguage();
    }
    return localStorage.getItem('cds-language') || document.documentElement.lang || 'es';
  }

  function t() {
    const lang = currentLang();
    return I18N[lang] || I18N.es;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatText(value) {
    return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  }

  function injectCss() {
    if (document.getElementById('cds-sommelier-css')) return;
    const link = document.createElement('link');
    link.id = 'cds-sommelier-css';
    link.rel = 'stylesheet';
    link.href = '/css/ai-sommelier.css';
    document.head.appendChild(link);
  }

  function buildUi() {
    const copy = t();
    const fab = document.createElement('button');
    fab.type = 'button';
    fab.className = 'cds-sommelier-fab';
    fab.setAttribute('aria-label', copy.fab);
    fab.innerHTML = `
      <span class="cds-sommelier-fab__mark" aria-hidden="true">CS</span>
      <span class="cds-sommelier-fab__pulse"></span>
    `;

    const panel = document.createElement('section');
    panel.className = 'cds-sommelier';
    panel.hidden = true;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', copy.title);
    panel.innerHTML = `
      <header class="cds-sommelier__header">
        <div class="cds-sommelier__mark" aria-hidden="true">CS</div>
        <div class="cds-sommelier__titles">
          <p class="cds-sommelier__kicker">${escapeHtml(copy.kicker)}</p>
          <h2 class="cds-sommelier__title">${escapeHtml(copy.title)}</h2>
        </div>
        <button type="button" class="cds-sommelier__close" aria-label="${escapeHtml(copy.close)}">×</button>
      </header>
      <div class="cds-sommelier__messages" data-messages></div>
      <div class="cds-sommelier__suggestions" data-suggestions>
        <button type="button" class="cds-sommelier__chip" data-prompt="${escapeHtml(copy.recommend)}">${escapeHtml(copy.recommend)}</button>
        <button type="button" class="cds-sommelier__chip" data-prompt="${escapeHtml(copy.b2b)}">${escapeHtml(copy.b2b)}</button>
        <button type="button" class="cds-sommelier__chip" data-prompt="${escapeHtml(copy.tasting)}">${escapeHtml(copy.tasting)}</button>
      </div>
      <a class="cds-sommelier__cta" data-whatsapp target="_blank" rel="noopener noreferrer">${escapeHtml(copy.whatsapp)}</a>
      <form class="cds-sommelier__form" data-form>
        <textarea class="cds-sommelier__input" rows="1" maxlength="2000" placeholder="${escapeHtml(copy.placeholder)}" data-input></textarea>
        <button type="submit" class="cds-sommelier__send" aria-label="${escapeHtml(copy.send)}" data-send>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M3.4 20.6 21 12 3.4 3.4l.1 6.8L15 12 3.5 13.8z"/></svg>
        </button>
      </form>
      <p class="cds-sommelier__disclaimer">${escapeHtml(copy.disclaimer)}</p>
    `;

    document.body.appendChild(fab);
    document.body.appendChild(panel);
    return { fab, panel };
  }

  function applyCopy(panel, fab) {
    const copy = t();
    fab.setAttribute('aria-label', copy.fab);
    panel.querySelector('.cds-sommelier__kicker').textContent = copy.kicker;
    panel.querySelector('.cds-sommelier__title').textContent = copy.title;
    panel.querySelector('.cds-sommelier__close').setAttribute('aria-label', copy.close);
    panel.querySelector('[data-input]').setAttribute('placeholder', copy.placeholder);
    panel.querySelector('[data-send]').setAttribute('aria-label', copy.send);
    panel.querySelector('[data-whatsapp]').textContent = copy.whatsapp;
    panel.querySelector('.cds-sommelier__disclaimer').textContent = copy.disclaimer;
    const chips = panel.querySelectorAll('[data-suggestions] .cds-sommelier__chip');
    const prompts = [copy.recommend, copy.b2b, copy.tasting];
    chips.forEach((chip, i) => {
      chip.textContent = prompts[i];
      chip.dataset.prompt = prompts[i];
    });
  }

  function appendMessage(container, role, text, extraClass) {
    const el = document.createElement('div');
    el.className = `cds-sommelier__msg cds-sommelier__msg--${role}${extraClass ? ' ' + extraClass : ''}`;
    el.innerHTML = formatText(text || '');
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return el;
  }

  function setStreaming(el, text) {
    el.innerHTML = `${formatText(text)}<span class="cds-sommelier__caret" aria-hidden="true"></span>`;
    el.parentElement.scrollTop = el.parentElement.scrollHeight;
  }

  async function consumeSse(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() || '';
      for (const block of blocks) {
        let event = 'message';
        let data = '';
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim();
          if (line.startsWith('data:')) data += line.slice(5).trim();
        }
        if (!data) continue;
        try {
          onEvent(event, JSON.parse(data));
        } catch {
          onEvent(event, { text: data });
        }
      }
    }
  }

  function init() {
    if (document.querySelector('.cds-sommelier-fab')) return;
    injectCss();
    const { fab, panel } = buildUi();
    const messagesEl = panel.querySelector('[data-messages]');
    const form = panel.querySelector('[data-form]');
    const input = panel.querySelector('[data-input]');
    const sendBtn = panel.querySelector('[data-send]');
    const suggestions = panel.querySelector('[data-suggestions]');
    const whatsappCta = panel.querySelector('[data-whatsapp]');
    const history = [];
    let busy = false;
    let greeted = false;

    function openPanel() {
      panel.hidden = false;
      fab.classList.add('is-open');
      sessionStorage.setItem(STORAGE_KEY, '1');
      if (!greeted) {
        appendMessage(messagesEl, 'bot', t().welcome);
        greeted = true;
      }
      input.focus();
    }

    function closePanel() {
      panel.hidden = true;
      fab.classList.remove('is-open');
      sessionStorage.removeItem(STORAGE_KEY);
    }

    function autoResize() {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 110) + 'px';
    }

    async function send(text) {
      const content = String(text || '').trim();
      if (!content || busy) return;
      busy = true;
      sendBtn.disabled = true;
      suggestions.hidden = true;
      appendMessage(messagesEl, 'user', content);
      history.push({ role: 'user', content });
      if (history.length > MAX_TURNS) history.splice(0, history.length - MAX_TURNS);
      input.value = '';
      autoResize();

      const botEl = appendMessage(messagesEl, 'bot', '');
      setStreaming(botEl, '');
      let assembled = '';

      try {
        const response = await fetch(API_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: history,
            language: currentLang(),
            page: window.location.pathname
          })
        });

        if (!response.ok) {
          let message = t().error;
          try {
            const json = await response.json();
            if (json && json.error) message = json.error;
          } catch {}
          throw new Error(message);
        }

        await consumeSse(response, (event, data) => {
          if (event === 'token' && data.text) {
            assembled += data.text;
            setStreaming(botEl, assembled);
          }
          if (event === 'lead' && data.whatsappUrl) {
            whatsappCta.href = data.whatsappUrl;
            whatsappCta.classList.add('is-visible');
          }
          if (event === 'error' && data.message) {
            assembled = data.message;
          }
          if (event === 'done' && data.text) {
            assembled = data.text;
          }
        });

        const finalText = assembled.trim() || t().error;
        botEl.innerHTML = formatText(finalText);
        history.push({ role: 'assistant', content: finalText });
      } catch (err) {
        botEl.classList.add('cds-sommelier__msg--error');
        botEl.textContent = (err && err.message) || t().error;
      } finally {
        busy = false;
        sendBtn.disabled = false;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }

    fab.addEventListener('click', () => {
      if (panel.hidden) openPanel();
      else closePanel();
    });
    panel.querySelector('.cds-sommelier__close').addEventListener('click', closePanel);
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      send(input.value);
    });
    input.addEventListener('input', autoResize);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send(input.value);
      }
    });
    suggestions.addEventListener('click', (e) => {
      const chip = e.target.closest('[data-prompt]');
      if (chip) send(chip.dataset.prompt);
    });
    window.addEventListener('cds:language-changed', () => applyCopy(panel, fab));

    if (sessionStorage.getItem(STORAGE_KEY) === '1' && !document.body.classList.contains('is-age-locked')) {
      openPanel();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
