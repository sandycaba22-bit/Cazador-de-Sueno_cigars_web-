/**
 * Cazador de Sueño Cigars SRL — Intro de ultra lujo (8 segundos exactos)
 */
(function () {
  'use strict';

  const INTRO_MS = 8000;
  const REVEAL_MS = 500;
  const RAMP_MS = 2000;
  const EMBER_BURST_MS = 2500;
  const TRANSITION_MS = 1400;
  const TOBACCO_VIDEO =
    'https://videos.pexels.com/video-files/3131277/3131277-hd_1920_1080_30fps.mp4';

  const intro = document.getElementById('intro');
  const site = document.getElementById('site');
  const smokeCanvas = document.getElementById('intro-smoke');
  const emberCanvas = document.getElementById('intro-embers');
  const introLogo = document.getElementById('intro-logo');
  const logoWrap = document.getElementById('intro-logo-wrap');
  const introVideo = document.querySelector('.intro__video');
  const navLogoLink = document.querySelector('.nav__logo');
  const navLogoCanvas = document.querySelector('.nav__logo-img');

  if (!intro || !site) return;

  function bootIntro() {
    runIntro();
  }

  function runIntro() {
  let animFrame = 0;
  let running = true;
  let startTime = 0;
  let logoReady = false;
  let introLogoSize = {
    w: 0,
    h: 0,
    displayH: window.innerWidth < 768 ? 180 : window.innerWidth < 1200 ? 230 : 280
  };

  /* ── Skip for reduced motion ── */
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    finishIntro(true);
    return;
  }

  document.body.classList.add('is-intro');
  site.setAttribute('aria-hidden', 'true');

  if (introVideo) {
    introVideo.src = TOBACCO_VIDEO;
    introVideo.play().catch(() => {});
  }

  /* ── PDF Logo render (intro) — fondo transparente ── */
  async function renderIntroLogo() {
    if (!window.LogoRender || !introLogo) return false;

    try {
      await LogoRender.renderPdfToCanvas(
        introLogo,
        'images/logo.pdf',
        introLogoSize.displayH
      );

      introLogoSize.w = parseFloat(introLogo.style.width) || introLogo.offsetWidth;
      introLogoSize.h = introLogoSize.displayH;
      logoReady = true;
      intro.classList.add('intro--logo-ready');
      return true;
    } catch (e) {
      console.warn('Intro logo render failed:', e);
      intro.classList.add('intro--logo-fallback');
      return false;
    }
  }

  /* ── Smoke particle system ── */
  class SmokeSystem {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.particles = [];
      this.resize();
      window.addEventListener('resize', () => this.resize());
    }

    resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = window.innerWidth * dpr;
      this.canvas.height = window.innerHeight * dpr;
      this.canvas.style.width = `${window.innerWidth}px`;
      this.canvas.style.height = `${window.innerHeight}px`;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.w = window.innerWidth;
      this.h = window.innerHeight;
    }

    spawn(intensity) {
      const cx = this.w * 0.5;
      const cy = this.h * 0.48;
      const count = Math.floor(intensity * 3);

      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: cx + (Math.random() - 0.5) * 320,
          y: cy + (Math.random() - 0.5) * 120 + 40,
          vx: (Math.random() - 0.5) * 0.35,
          vy: -0.25 - Math.random() * 0.55,
          r: 18 + Math.random() * 42,
          life: 0,
          maxLife: 180 + Math.random() * 220,
          rot: Math.random() * Math.PI * 2,
          drift: (Math.random() - 0.5) * 0.008
        });
      }

      if (this.particles.length > 220) {
        this.particles.splice(0, this.particles.length - 220);
      }
    }

    update() {
      for (let i = this.particles.length - 1; i >= 0; i--) {
        const p = this.particles[i];
        p.life++;
        p.x += p.vx + Math.sin(p.life * 0.02) * 0.15;
        p.y += p.vy;
        p.r += 0.14;
        p.rot += p.drift;
        p.vx *= 0.998;

        if (p.life > p.maxLife) this.particles.splice(i, 1);
      }
    }

    draw() {
      this.ctx.clearRect(0, 0, this.w, this.h);

      for (const p of this.particles) {
        const t = p.life / p.maxLife;
        const alpha = t < 0.15
          ? t / 0.15 * 0.22
          : (1 - t) * 0.28;

        const grad = this.ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
        grad.addColorStop(0, `rgba(210, 210, 210, ${alpha * 0.9})`);
        grad.addColorStop(0.35, `rgba(140, 140, 140, ${alpha * 0.55})`);
        grad.addColorStop(0.7, `rgba(80, 80, 80, ${alpha * 0.2})`);
        grad.addColorStop(1, 'rgba(30, 30, 30, 0)');

        this.ctx.save();
        this.ctx.translate(p.x, p.y);
        this.ctx.rotate(p.rot);
        this.ctx.scale(1.3, 0.85);
        this.ctx.fillStyle = grad;
        this.ctx.beginPath();
        this.ctx.arc(0, 0, p.r, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
      }
    }
  }

  /* ── Ember / fire spark system ── */
  class EmberSystem {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.sparks = [];
      this.resize();
      window.addEventListener('resize', () => this.resize());
    }

    resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = window.innerWidth * dpr;
      this.canvas.height = window.innerHeight * dpr;
      this.canvas.style.width = `${window.innerWidth}px`;
      this.canvas.style.height = `${window.innerHeight}px`;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.w = window.innerWidth;
      this.h = window.innerHeight;
    }

    spawnFromLogo(elapsed) {
      if (!logoWrap) return;

      const rect = logoWrap.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const rx = rect.width * 0.52;
      const ry = rect.height * 0.48;
      const burst = elapsed < EMBER_BURST_MS ? 2.2 : 0.9;
      const count = Math.floor(2 + burst * Math.random() * 3);

      const colors = ['#e8d5a3', '#c9a962', '#ff9a3c', '#ffd700', '#b87333'];

      for (let i = 0; i < count; i++) {
        const angle = Math.random() * Math.PI * 2;
        const edge = 0.85 + Math.random() * 0.2;
        const x = cx + Math.cos(angle) * rx * edge;
        const y = cy + Math.sin(angle) * ry * edge;
        const speed = 0.4 + Math.random() * 1.6;

        this.sparks.push({
          x,
          y,
          vx: Math.cos(angle) * speed * 0.6 + (Math.random() - 0.5) * 0.8,
          vy: -Math.abs(Math.sin(angle)) * speed - Math.random() * 1.2,
          life: 0,
          maxLife: 30 + Math.random() * 50,
          size: 0.6 + Math.random() * 2.2,
          color: colors[Math.floor(Math.random() * colors.length)],
          glow: 4 + Math.random() * 10
        });
      }

      if (this.sparks.length > 350) {
        this.sparks.splice(0, this.sparks.length - 350);
      }
    }

    update() {
      for (let i = this.sparks.length - 1; i >= 0; i--) {
        const s = this.sparks[i];
        s.life++;
        s.x += s.vx;
        s.y += s.vy;
        s.vy -= 0.018;
        s.vx *= 0.985;
        s.size *= 0.992;

        if (s.life > s.maxLife || s.size < 0.2) this.sparks.splice(i, 1);
      }
    }

    draw() {
      this.ctx.clearRect(0, 0, this.w, this.h);
      this.ctx.globalCompositeOperation = 'lighter';

      for (const s of this.sparks) {
        const t = 1 - s.life / s.maxLife;
        this.ctx.shadowBlur = s.glow * t;
        this.ctx.shadowColor = s.color;
        this.ctx.fillStyle = s.color;
        this.ctx.globalAlpha = t * 0.95;
        this.ctx.beginPath();
        this.ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
        this.ctx.fill();
      }

      this.ctx.globalAlpha = 1;
      this.ctx.shadowBlur = 0;
      this.ctx.globalCompositeOperation = 'source-over';
    }
  }

  const smoke = new SmokeSystem(smokeCanvas);
  const embers = new EmberSystem(emberCanvas);

  /* ── Main animation loop ── */
  function tick(now) {
    if (!running) return;

    if (!startTime) startTime = now;
    const elapsed = now - startTime;

    if (elapsed < INTRO_MS) {
      const intensity = elapsed < RAMP_MS ? elapsed / RAMP_MS : 1;
      smoke.spawn(intensity * 0.65);
      embers.spawnFromLogo(elapsed);
    }

    smoke.update();
    embers.update();
    smoke.draw();
    embers.draw();

    if (elapsed >= REVEAL_MS && !intro.classList.contains('intro--reveal')) {
      intro.classList.add('intro--reveal');
    }

    if (elapsed >= INTRO_MS && !intro.classList.contains('intro--exiting')) {
      beginExit();
    }

    animFrame = requestAnimationFrame(tick);
  }

  /* ── Logo flies to nav ── */
  function beginExit() {
    intro.classList.add('intro--exiting');
    running = false;

    const navRect = navLogoLink.getBoundingClientRect();
    const wrapRect = logoWrap.getBoundingClientRect();

    const navCX = navRect.left + navRect.width / 2;
    const navCY = navRect.top + navRect.height / 2;
    const scale = (navRect.height * 0.85) / wrapRect.height;

    const dx = navCX - window.innerWidth / 2;
    const dy = navCY - window.innerHeight / 2;

    logoWrap.style.transform =
      `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(${scale})`;

    setTimeout(finishIntro, TRANSITION_MS);
  }

  function finishIntro(instant) {
    running = false;
    cancelAnimationFrame(animFrame);

    intro.classList.add('intro--done');
    document.body.classList.remove('is-intro');
    document.body.classList.add('site-revealed');
    site.setAttribute('aria-hidden', 'false');

    if (navLogoCanvas) {
      navLogoCanvas.classList.add('logo-canvas--ready');
    }

    setTimeout(() => {
      intro.remove();
      document.body.style.overflow = '';
    }, instant ? 0 : 600);

    window.dispatchEvent(new CustomEvent('intro:complete'));
  }

  /* ── Boot ── */
  document.body.style.overflow = 'hidden';

  renderIntroLogo().then(() => {
    requestAnimationFrame((t) => {
      startTime = t;
      animFrame = requestAnimationFrame(tick);
    });
  });

  setTimeout(() => {
    if (!intro.classList.contains('intro--done')) {
      beginExit();
    }
  }, INTRO_MS + 200);
  }

  if (localStorage.getItem('cds-age-verified') === '1') {
    bootIntro();
  } else {
    window.addEventListener('cds:age-verified', bootIntro, { once: true });
  }
})();
