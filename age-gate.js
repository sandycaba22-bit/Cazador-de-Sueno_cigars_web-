/**
 * Age Gate — bloqueo obligatorio hasta verificación de edad (21+)
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'cds-age-verified';
  const gate = document.getElementById('age-gate');
  const enter = document.getElementById('age-enter');
  const exit = document.getElementById('age-exit');

  function lock() {
    document.body.classList.add('is-age-locked');
    document.body.style.overflow = 'hidden';
    if (gate) {
      gate.classList.remove('age-gate--hidden');
      gate.setAttribute('aria-hidden', 'false');
    }
  }

  function unlock() {
    document.body.classList.remove('is-age-locked');
    if (gate) {
      gate.classList.add('age-gate--hidden');
      gate.setAttribute('aria-hidden', 'true');
    }
    window.dispatchEvent(new CustomEvent('cds:age-verified'));
  }

  if (localStorage.getItem(STORAGE_KEY) === '1') {
    document.body.classList.remove('is-age-locked');
    if (gate) gate.classList.add('age-gate--hidden');
  } else {
    lock();
  }

  if (enter) {
    enter.addEventListener('click', () => {
      localStorage.setItem(STORAGE_KEY, '1');
      unlock();
    });
  }

  if (exit) {
    exit.addEventListener('click', () => {
      window.location.replace('https://www.google.com');
    });
  }
})();
