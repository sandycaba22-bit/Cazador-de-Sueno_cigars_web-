/**
 * Renderiza logo PDF con fondo 100% transparente
 */
window.LogoRender = {
  removeBackground(canvas) {
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas;
    const imageData = ctx.getImageData(0, 0, width, height);
    const d = imageData.data;

    for (let i = 0; i < d.length; i += 4) {
      const r = d[i];
      const g = d[i + 1];
      const b = d[i + 2];
      const lum = 0.299 * r + 0.587 * g + 0.114 * b;
      const maxC = Math.max(r, g, b);
      const minC = Math.min(r, g, b);
      const sat = maxC === 0 ? 0 : (maxC - minC) / maxC;

      /* Blanco / gris claro del render PDF */
      if (r > 220 && g > 220 && b > 220) {
        d[i + 3] = 0;
        continue;
      }

      /* Grises claros sin saturación (fondo) */
      if (lum > 190 && sat < 0.12) {
        d[i + 3] = 0;
        continue;
      }

      /* Negro puro del PDF — transparente sobre fondo oscuro */
      if (lum < 32 && sat < 0.2) {
        d[i + 3] = 0;
        continue;
      }

      /* Antialiasing en bordes oscuros */
      if (lum < 60 && sat < 0.28) {
        d[i + 3] = Math.round(d[i + 3] * Math.max(0, (lum - 18) / 42));
      }
    }

    ctx.putImageData(imageData, 0, 0);
  },

  async mountAll() {
    if (!window.pdfjsLib) return;
    const canvases = document.querySelectorAll('.logo-canvas[data-logo]');
    await Promise.all(
      Array.from(canvases).map(async (canvas) => {
        try {
          const h = Number(canvas.dataset.height) || 44;
          await this.renderPdfToCanvas(canvas, canvas.dataset.logo, h);
          canvas.classList.add('logo-canvas--ready');
        } catch (e) {
          console.warn('Logo render failed:', e);
        }
      })
    );
  },

  async renderPdfToCanvas(canvas, url, targetHeight) {
    if (!window.pdfjsLib) return false;

    pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    const pdf = await pdfjsLib.getDocument(url).promise;
    const page = await pdf.getPage(1);
    const base = page.getViewport({ scale: 1 });
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const displayScale = targetHeight / base.height;
    const viewport = page.getViewport({ scale: displayScale * dpr });
    const ctx = canvas.getContext('2d');

    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.style.width = `${base.width * displayScale}px`;
    canvas.style.height = `${targetHeight}px`;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    await page.render({ canvasContext: ctx, viewport }).promise;
    this.removeBackground(canvas);

    return true;
  }
};

document.addEventListener('DOMContentLoaded', () => {
  if (window.LogoRender && typeof window.LogoRender.mountAll === 'function') {
    window.LogoRender.mountAll();
  }
});
