(function () {
  'use strict';

  var COOKIE_NAME = 'cds_age_gate';
  var COOKIE_VALUE = 'accepted';
  var COOKIE_DAYS = 180;
  var LEGACY_STORAGE = 'cds-age-verified';

  function getCookie(name) {
    var pattern = new RegExp('(?:^|; )' + name.replace(/[-[\]/{}()*+?.\\^$|]/g, '\\$&') + '=([^;]*)');
    var match = document.cookie.match(pattern);
    return match ? decodeURIComponent(match[1]) : null;
  }

  function setCookie(name, value, days) {
    var expires = new Date();
    expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie =
      name +
      '=' +
      encodeURIComponent(value) +
      '; expires=' +
      expires.toUTCString() +
      '; path=/; SameSite=Lax';
  }

  function isAccepted() {
    if (getCookie(COOKIE_NAME) === COOKIE_VALUE) {
      return true;
    }

    try {
      if (localStorage.getItem(LEGACY_STORAGE) === '1') {
        setCookie(COOKIE_NAME, COOKIE_VALUE, COOKIE_DAYS);
        localStorage.removeItem(LEGACY_STORAGE);
        return true;
      }
    } catch (error) {
      /* ignore storage failures */
    }

    return false;
  }

  function lockPage() {
    document.documentElement.classList.add('age-gate-pending');
    document.body.classList.add('age-gate-open', 'is-age-locked');
  }

  function unlockPage() {
    document.documentElement.classList.remove('age-gate-pending');
    document.body.classList.remove('age-gate-open', 'is-age-locked');
    document.body.style.overflow = '';
    window.dispatchEvent(new CustomEvent('cds:age-verified'));
  }

  function hideGate(gate) {
    gate.setAttribute('aria-hidden', 'true');
    gate.classList.remove('is-denied');
    gate.classList.add('age-gate--hidden');
  }

  function handleExit() {
    window.location.replace('https://www.google.com');
  }

  document.addEventListener('DOMContentLoaded', function () {
    var gate = document.querySelector('[data-age-gate]') || document.getElementById('age-gate');
    if (!gate) return;

    var acceptButton = gate.querySelector('[data-age-gate-accept]') || document.getElementById('age-enter');
    var denyButton = gate.querySelector('[data-age-gate-deny]');
    var legacyExit = document.getElementById('age-exit');
    var feedback = gate.querySelector('[data-age-gate-feedback]');
    var exitLink = gate.querySelector('[data-age-gate-exit]');
    var alreadyAccepted = isAccepted();

    if (alreadyAccepted) {
      hideGate(gate);
      unlockPage();
      return;
    }

    lockPage();
    gate.setAttribute('aria-hidden', 'false');

    if (acceptButton) {
      acceptButton.addEventListener('click', function () {
        setCookie(COOKIE_NAME, COOKIE_VALUE, COOKIE_DAYS);
        hideGate(gate);
        unlockPage();
      });
    }

    if (denyButton) {
      denyButton.addEventListener('click', function () {
        gate.classList.add('is-denied');
        gate.setAttribute('aria-hidden', 'false');

        if (feedback) {
          feedback.textContent =
            'Debes tener 21 años o más para acceder a este sitio. Gracias por respetar esta verificación.';
        }

        if (exitLink) {
          exitLink.hidden = false;
          exitLink.focus();
          exitLink.addEventListener('click', function (event) {
            event.preventDefault();
            handleExit();
          });
        }
      });
    }

    if (legacyExit) {
      legacyExit.addEventListener('click', function (event) {
        event.preventDefault();
        handleExit();
      });
    }
  });
})();
