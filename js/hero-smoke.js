/**
 * Humo champagne desde cada letra del título de bienvenida.
 * Canvas 2D ligero (~48 partículas máx.), 60fps, se pausa fuera de vista.
 */
(function () {
  'use strict';

  var MAX_PARTICLES = 48;
  var SPAWN_PER_FRAME = 0.35;
  var RISE_PX = 88;
  var TITLE_SELECTOR = '.hero-premium--welcome [data-hero-smoke]';

  function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function ageGateBlocking() {
    return (
      document.documentElement.classList.contains('age-gate-pending') ||
      document.body.classList.contains('age-gate-open') ||
      document.body.classList.contains('is-age-locked')
    );
  }

  function letterAnchors(title) {
    var textNode = null;
    for (var i = 0; i < title.childNodes.length; i += 1) {
      if (title.childNodes[i].nodeType === Node.TEXT_NODE && title.childNodes[i].textContent.trim()) {
        textNode = title.childNodes[i];
        break;
      }
    }
    if (!textNode) return [];

    var raw = textNode.textContent;
    var anchors = [];
    var range = document.createRange();

    for (var index = 0; index < raw.length; index += 1) {
      if (/\s/.test(raw.charAt(index))) continue;
      range.setStart(textNode, index);
      range.setEnd(textNode, index + 1);
      var rect = range.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) continue;
      anchors.push({
        x: rect.left + rect.width * 0.5,
        y: rect.top + rect.height * 0.12,
        w: rect.width,
      });
    }

    return anchors;
  }

  function createParticle(anchor, stageRect) {
    var jitter = (Math.random() - 0.5) * Math.max(4, anchor.w * 0.55);
    return {
      x: anchor.x - stageRect.left + jitter,
      y: anchor.y - stageRect.top + RISE_PX + (Math.random() * 3),
      vx: (Math.random() - 0.5) * 0.18,
      vy: -(0.22 + Math.random() * 0.28),
      life: 1,
      decay: 0.0045 + Math.random() * 0.0035,
      size: 3.5 + Math.random() * 5.5,
      wobble: Math.random() * Math.PI * 2,
      wobbleSpeed: 0.012 + Math.random() * 0.018,
    };
  }

  function init() {
    if (prefersReducedMotion()) return;

    var title = document.querySelector(TITLE_SELECTOR);
    if (!title) return;

    var stage = title.closest('.hero-smoke-stage') || title.parentElement;
    if (!stage) return;

    if (!stage.classList.contains('hero-smoke-stage')) {
      var wrap = document.createElement('div');
      wrap.className = 'hero-smoke-stage';
      title.parentNode.insertBefore(wrap, title);
      wrap.appendChild(title);
      stage = wrap;
    }

    var canvas = stage.querySelector('.hero-smoke-canvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.className = 'hero-smoke-canvas';
      canvas.setAttribute('aria-hidden', 'true');
      stage.insertBefore(canvas, title);
    }

    var ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    var particles = [];
    var spawnBudget = 0;
    var running = false;
    var visible = true;
    var raf = 0;
    var dpr = 1;

    function resize() {
      var rect = stage.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      var width = Math.max(1, Math.ceil(rect.width));
      var height = Math.max(1, Math.ceil(rect.height + RISE_PX));
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = width + 'px';
      canvas.style.height = height + 'px';
      canvas.style.top = -RISE_PX + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function drawParticle(p) {
      var fade = Math.pow(p.life, 1.35);
      var radius = p.size * (0.65 + (1 - p.life) * 1.1);
      var gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
      gradient.addColorStop(0, 'rgba(232, 213, 170,' + (0.22 * fade).toFixed(3) + ')');
      gradient.addColorStop(0.45, 'rgba(212, 175, 55,' + (0.1 * fade).toFixed(3) + ')');
      gradient.addColorStop(1, 'rgba(197, 160, 89, 0)');
      ctx.beginPath();
      ctx.fillStyle = gradient;
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx.fill();
    }

    function tick() {
      raf = 0;
      if (!running || !visible || ageGateBlocking() || document.hidden) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
      }

      var stageRect = stage.getBoundingClientRect();
      var anchors = letterAnchors(title);
      spawnBudget += SPAWN_PER_FRAME;

      while (spawnBudget >= 1 && particles.length < MAX_PARTICLES && anchors.length) {
        spawnBudget -= 1;
        var anchor = anchors[(Math.random() * anchors.length) | 0];
        particles.push(createParticle(anchor, stageRect));
      }

      ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);

      var ceiling = 8;
      for (var i = particles.length - 1; i >= 0; i -= 1) {
        var p = particles[i];
        p.wobble += p.wobbleSpeed;
        p.x += p.vx + Math.sin(p.wobble) * 0.22;
        p.y += p.vy;
        p.life -= p.decay;
        p.size *= 1.004;

        if (p.life <= 0 || p.y < ceiling) {
          particles.splice(i, 1);
          continue;
        }

        drawParticle(p);
      }

      raf = window.requestAnimationFrame(tick);
    }

    function start() {
      if (running || prefersReducedMotion()) return;
      running = true;
      resize();
      if (!raf) raf = window.requestAnimationFrame(tick);
    }

    function stop() {
      running = false;
      if (raf) {
        window.cancelAnimationFrame(raf);
        raf = 0;
      }
      particles.length = 0;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    var observer = new IntersectionObserver(
      function (entries) {
        visible = entries.some(function (entry) {
          return entry.isIntersecting;
        });
        if (visible && !ageGateBlocking()) start();
        else if (!visible) stop();
      },
      { threshold: 0.2 }
    );
    observer.observe(stage);

    var resizeTimer = 0;
    window.addEventListener(
      'resize',
      function () {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(function () {
          if (running) resize();
        }, 120);
      },
      { passive: true }
    );

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stop();
      else if (visible && !ageGateBlocking()) start();
    });

    window.addEventListener('cds:age-verified', function () {
      if (visible) start();
    });

    if (!ageGateBlocking() && visible) start();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
