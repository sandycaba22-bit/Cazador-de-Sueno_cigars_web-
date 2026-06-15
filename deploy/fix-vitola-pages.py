# -*- coding: utf-8 -*-
import re
from pathlib import Path

VITOLAS = Path(r"C:\Users\sandy\cazador-de-suenos-cigars\vitolas")
FONT_OLD = re.compile(
    r'<link href="https://fonts\.googleapis\.com/css2\?family=[^"]+" rel="stylesheet">'
)
FONT_NEW = (
    '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond'
    ':ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Libre+Baskerville'
    ':ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">'
)

AGE_GATE = """  <div id="age-gate" class="age-gate" role="dialog" aria-labelledby="age-gate-title" aria-modal="true" aria-hidden="false">
    <div class="age-gate__splash">
      <p class="age-gate__label">Verificación de Edad</p>
      <h1 class="age-gate__title" id="age-gate-title">Cazador de Sueños Cigars</h1>
      <p class="age-gate__text">Este sitio contiene información sobre productos de tabaco reservados para mayores de edad. Confirme que tiene 21 años o más para continuar.</p>
      <div class="age-gate__actions">
        <button type="button" class="btn btn--primary age-gate__enter" id="age-enter">Sí, tengo 21 años o más</button>
        <button type="button" class="age-gate__exit" id="age-exit">No, salir del sitio</button>
      </div>
      <p class="age-gate__legal">Al ingresar, usted confirma cumplir con la edad legal en su jurisdicción.</p>
    </div>
  </div>
  <script src="../age-gate.js"></script>"""

NAV = """        <li class="nav__item nav__item--has-menu">
          <button type="button" class="nav__menu-trigger" aria-haspopup="true" aria-expanded="false">Vitolas</button>
          <div class="nav__menu" role="menu" aria-label="Colección oficial">
            <a role="menuitem" href="el-emperador.html" class="nav__menu-entry">
              <span class="nav__menu-name">El Emperador</span>
              <span class="nav__menu-desc">El Primer Sueño</span>
            </a>
            <a role="menuitem" href="puro-habano.html" class="nav__menu-entry">
              <span class="nav__menu-name">Puro Habano</span>
              <span class="nav__menu-desc">Raíces Cubanas</span>
            </a>
            <a role="menuitem" href="el-exquisito.html" class="nav__menu-entry">
              <span class="nav__menu-name">El Exquisito</span>
              <span class="nav__menu-desc">Edición de Autor</span>
            </a>
            <a role="menuitem" href="el-rango.html" class="nav__menu-entry">
              <span class="nav__menu-name">El Rango</span>
              <span class="nav__menu-desc">Formato Figurado</span>
            </a>
            <a role="menuitem" href="ligero-007.html" class="nav__menu-entry">
              <span class="nav__menu-name">Ligero 007</span>
              <span class="nav__menu-desc">Obra Maestra</span>
            </a>
            <a role="menuitem" href="el-sultan.html" class="nav__menu-entry">
              <span class="nav__menu-name">El Sultán</span>
              <span class="nav__menu-desc">Valle del Cibao</span>
            </a>
            <span class="nav__menu-divider" aria-hidden="true"></span>
            <a role="menuitem" href="../index.html#catalogo" class="nav__menu-all">Colección completa</a>
          </div>
        </li>"""

for path in VITOLAS.glob("*.html"):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = FONT_OLD.sub(FONT_NEW, text, count=1)
    text = re.sub(r'<body class="[^"]*">', '<body class="vitola-page is-age-locked">', text, count=1)
    text = re.sub(
        r'  <div id="age-gate" class="age-gate"[\s\S]*?</div>\s*',
        AGE_GATE + "\n\n",
        text,
        count=1,
    )
    text = re.sub(
        r'<li class="nav__item nav__item--has-menu">[\s\S]*?</li>\s*<li><a href="\.\./index\.html#contacto"',
        NAV + '\n        <li><a href="../index.html#contacto"',
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")
    print("ok", path.name)
