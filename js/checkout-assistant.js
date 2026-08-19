/**
 * Asistente de checkout.
 *
 * Deliberadamente aislado del carrito y del pago:
 *  - Se carga con defer y se monta después del checkout. Si este archivo falla
 *    o no llega, la compra sigue funcionando igual.
 *  - Solo lee estado a través de window.CDS_CHECKOUT.getState(). No escribe en
 *    el carrito, no toca el formulario y no puede enviar un pedido.
 *  - Habla con el servicio del sommelier (puerto 8787), no con el de comercio.
 *    Un modelo de lenguaje lento no puede frenar una transacción.
 */

(function () {
  'use strict';

  const ENDPOINT = '/api/ai-sommelier/checkout';
  const MAX_HISTORY = 12;

  const history = [];
  let panel = null;
  let stream = null;
  let lastError = '';
  let opened = false;

  // -------------------------------------------------------------- montaje

  function mount() {
    if (document.getElementById('ca-root')) return;

    const root = document.createElement('div');
    root.id = 'ca-root';
    root.className = 'ca';
    root.innerHTML = `
      <button type="button" class="ca__fab" id="ca-fab" aria-expanded="false" aria-controls="ca-panel" aria-label="Concierge de pago">
        <span class="ca__fab-dot" id="ca-dot" hidden></span>
        <span class="ca__fab-mark" aria-hidden="true">CS</span>
        <span class="ca__fab-pulse" aria-hidden="true"></span>
        <span class="ca__fab-label">Concierge de pago</span>
      </button>
      <section class="ca__panel" id="ca-panel" role="dialog" aria-label="Concierge de pago" hidden>
        <header class="ca__head">
          <div class="ca__head-mark" aria-hidden="true">CS</div>
          <div>
            <p class="ca__head-kicker">Cazador de Sueños</p>
            <strong>Concierge de pago</strong>
            <small>Transferencia, PayPal o envío — sin datos de tarjeta</small>
          </div>
          <button type="button" class="ca__close" id="ca-close" aria-label="Cerrar">×</button>
        </header>
        <div class="ca__log" id="ca-log" aria-live="polite"></div>
        <div class="ca__chips" id="ca-chips"></div>
        <form class="ca__form" id="ca-form">
          <input
            type="text"
            id="ca-input"
            placeholder="Escribe tu duda…"
            autocomplete="off"
            maxlength="500"
          />
          <button type="submit" aria-label="Enviar">→</button>
        </form>
        <p class="ca__legal">No escribas datos de tarjeta aquí. Nunca te los pediremos por chat.</p>
      </section>`;

    document.body.appendChild(root);
    panel = document.getElementById('ca-panel');

    document.getElementById('ca-fab').addEventListener('click', toggle);
    document.getElementById('ca-close').addEventListener('click', () => toggle(false));
    document.getElementById('ca-form').addEventListener('submit', onSubmit);

    renderChips([
      '¿Cómo pago con tarjeta?',
      '¿Cómo pago con PayPal?',
      '¿Cómo hago la transferencia?',
      'Mi tarjeta fue rechazada',
    ]);
  }

  function toggle(force) {
    const open = typeof force === 'boolean' ? force : !opened;
    opened = open;
    panel.hidden = !open;
    const fab = document.getElementById('ca-fab');
    fab.setAttribute('aria-expanded', String(open));
    fab.classList.toggle('is-open', open);
    document.getElementById('ca-dot').hidden = true;

    if (open && !history.length) {
      addMessage(
        'assistant',
        'Bienvenido. Soy el concierge de la casa: transferencia bancaria (RD o EE.UU.), PayPal o cualquier duda sobre su pedido.'
      );
    }
    if (open) document.getElementById('ca-input').focus();
  }

  // ---------------------------------------------------------- mensajería

  function addMessage(role, text) {
    const log = document.getElementById('ca-log');
    const bubble = document.createElement('div');
    bubble.className = `ca__msg ca__msg--${role}`;
    bubble.textContent = text;
    log.appendChild(bubble);
    log.scrollTop = log.scrollHeight;
    return bubble;
  }

  function renderChips(items) {
    const chips = document.getElementById('ca-chips');
    chips.innerHTML = items
      .map((item) => `<button type="button" class="ca__chip">${item}</button>`)
      .join('');
    chips.querySelectorAll('.ca__chip').forEach((chip) => {
      chip.addEventListener('click', () => send(chip.textContent));
    });
  }

  function checkoutState() {
    try {
      const state = window.CDS_CHECKOUT ? window.CDS_CHECKOUT.getState() : {};
      return { ...state, lastError };
    } catch {
      return { lastError };
    }
  }

  function onSubmit(event) {
    event.preventDefault();
    const input = document.getElementById('ca-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    send(text);
  }

  async function send(text) {
    if (stream) return;

    addMessage('user', text);
    history.push({ role: 'user', content: text });
    document.getElementById('ca-chips').innerHTML = '';

    const bubble = addMessage('assistant', '…');
    let answer = '';
    stream = true;

    try {
      const response = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: history.slice(-MAX_HISTORY),
          language: document.documentElement.lang || 'es',
          context: checkoutState(),
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error('sin respuesta');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() || '';

        for (const chunk of chunks) {
          const eventLine = chunk.match(/^event:\s*(.+)$/m);
          const dataLine = chunk.match(/^data:\s*(.+)$/m);
          if (!eventLine || !dataLine) continue;

          let data;
          try {
            data = JSON.parse(dataLine[1]);
          } catch {
            continue;
          }

          if (eventLine[1] === 'token' && data.text) {
            answer += data.text;
            bubble.textContent = answer;
            document.getElementById('ca-log').scrollTop = 1e6;
          } else if (eventLine[1] === 'error') {
            answer = data.message || 'No pude responder ahora mismo.';
            bubble.textContent = answer;
          }
        }
      }

      if (!answer) {
        answer = 'No pude responder ahora mismo. Escríbanos por WhatsApp y le atendemos de inmediato.';
        bubble.textContent = answer;
      }

      history.push({ role: 'assistant', content: answer });
    } catch {
      bubble.textContent =
        'El asistente no está disponible en este momento. Escríbanos por WhatsApp y completamos su pedido.';
    } finally {
      stream = null;
    }
  }

  // ------------------------------------------------- ayuda proactiva

  /**
   * Cuando el checkout falla, el asistente se ofrece en lugar de esperar a que
   * el cliente lo descubra. Es el momento exacto en que se abandona el carrito.
   */
  window.addEventListener('checkout:error', (event) => {
    lastError = (event.detail && event.detail.message) || '';
    if (opened) return;
    document.getElementById('ca-dot').hidden = false;
    renderChips(['¿Por qué falló mi pago?', 'Quiero pagar por transferencia']);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
