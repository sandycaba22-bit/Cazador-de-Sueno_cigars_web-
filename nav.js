/**
 * Navegación — menú Vitolas (dropdown) y móvil
 */
(function () {
  'use strict';

  const header = document.querySelector('.site-header');
  const toggle = document.querySelector('.nav__toggle');
  const nav = document.querySelector('.nav__links');
  const menuItem = document.querySelector('.nav__item--has-menu');
  const menuTrigger = document.querySelector('.nav__menu-trigger');

  if (header) {
    window.addEventListener('scroll', () => {
      header.classList.toggle('site-header--scrolled', window.scrollY > 60);
    }, { passive: true });
  }

  function closeVitolasMenu() {
    if (!menuItem) return;
    menuItem.classList.remove('nav__item--open');
    if (menuTrigger) menuTrigger.setAttribute('aria-expanded', 'false');
  }

  function openVitolasMenu() {
    if (!menuItem) return;
    menuItem.classList.add('nav__item--open');
    if (menuTrigger) menuTrigger.setAttribute('aria-expanded', 'true');
  }

  function toggleVitolasMenu() {
    if (!menuItem) return;
    const isOpen = menuItem.classList.toggle('nav__item--open');
    if (menuTrigger) menuTrigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  }

  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('nav__links--open');
      toggle.setAttribute('aria-expanded', open);
      if (!open) closeVitolasMenu();
    });
  }

  if (menuTrigger && menuItem) {
    menuTrigger.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleVitolasMenu();
    });

    const desktopMq = window.matchMedia('(min-width: 769px) and (hover: hover)');

    function bindDesktopHover() {
      if (!desktopMq.matches) return;
      menuItem.addEventListener('mouseenter', openVitolasMenu);
      menuItem.addEventListener('mouseleave', closeVitolasMenu);
    }

    bindDesktopHover();
    desktopMq.addEventListener('change', () => {
      menuItem.removeEventListener('mouseenter', openVitolasMenu);
      menuItem.removeEventListener('mouseleave', closeVitolasMenu);
      closeVitolasMenu();
      bindDesktopHover();
    });

    document.addEventListener('click', (e) => {
      if (!menuItem.contains(e.target)) closeVitolasMenu();
    });

    menuTrigger.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeVitolasMenu();
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleVitolasMenu();
      }
    });
  }

  if (nav) {
    nav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        nav.classList.remove('nav__links--open');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
        closeVitolasMenu();
      });
    });
  }
})();
