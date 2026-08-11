/**
 * Hero — parallax imperceptible sobre la fotografía de fondo
 */
(function () {
  'use strict';

  var hero = document.getElementById('hero');
  var photo = document.getElementById('heroPhotoWrap');
  if (!hero || !photo) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var x = 0;
  var y = 0;
  var targetX = 0;
  var targetY = 0;

  hero.addEventListener('mousemove', function (event) {
    var rect = hero.getBoundingClientRect();
    targetX = (event.clientX - rect.left) / rect.width - 0.5;
    targetY = (event.clientY - rect.top) / rect.height - 0.5;
  });

  hero.addEventListener('mouseleave', function () {
    targetX = 0;
    targetY = 0;
  });

  function tick() {
    x += (targetX - x) * 0.055;
    y += (targetY - y) * 0.055;
    photo.style.transform =
      'translate3d(' + (x * 14) + 'px,' + (y * 10) + 'px,0) scale(1.05)';
    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
})();
