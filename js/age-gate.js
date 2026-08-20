(function () {
  var COOKIE_NAME = 'cds_age_gate';
  var COOKIE_VALUE = 'accepted';
  var COOKIE_DAYS = 180;

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

  function lockPage() {
    document.documentElement.classList.add('age-gate-pending');
    document.body.classList.add('age-gate-open');
  }

  function unlockPage() {
    document.documentElement.classList.remove('age-gate-pending');
    document.body.classList.remove('age-gate-open');
  }

  function handleExit() {
    if (window.history.length > 1) {
      window.history.back();
      return;
    }

    window.location.replace('https://www.google.com');
  }

  document.addEventListener('DOMContentLoaded', function () {
    var gate = document.querySelector('[data-age-gate]');
    if (!gate) return;

    var acceptButton = gate.querySelector('[data-age-gate-accept]');
    var denyButton = gate.querySelector('[data-age-gate-deny]');
    var feedback = gate.querySelector('[data-age-gate-feedback]');
    var exitLink = gate.querySelector('[data-age-gate-exit]');
    var alreadyAccepted = getCookie(COOKIE_NAME) === COOKIE_VALUE;

    gate.setAttribute('aria-hidden', alreadyAccepted ? 'true' : 'false');

    if (alreadyAccepted) {
      unlockPage();
      return;
    }

    lockPage();

    if (acceptButton) {
      acceptButton.addEventListener('click', function () {
        setCookie(COOKIE_NAME, COOKIE_VALUE, COOKIE_DAYS);
        gate.setAttribute('aria-hidden', 'true');
        gate.classList.remove('is-denied');
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
  });
})();
