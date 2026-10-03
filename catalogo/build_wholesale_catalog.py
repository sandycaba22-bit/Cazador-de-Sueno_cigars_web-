"""Genera los catálogos mayoristas ES y EN.

Cada ficha, de arriba abajo: fotos reales, especificaciones, nota de cata.
"""

import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as FlowImage,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FONT_DIR = Path(r"C:\Windows\Fonts")

NAVY = HexColor("#0C1424")
CREAM = HexColor("#F7F4EE")
INK = HexColor("#1C1612")
MUTED = HexColor("#5C5348")
GOLD = HexColor("#C4A35A")
GOLD_DEEP = HexColor("#8C6A2F")
LINE = HexColor("#C4A574")

WELCOME = {
    "es": (
        "Bienvenido a nuestro portal B2B exclusivo. En Cazador de Sueños elaboramos "
        "puros premium 100% hechos a mano por maestros tabaqueros en la República "
        "Dominicana, listos para la exportación global con facilidades comerciales y RNC válido."
    ),
    "en": (
        "Welcome to our exclusive B2B portal. At Cazador de Sueños, we craft 100% handmade "
        "premium cigars by master torcedores in the Dominican Republic, fully equipped for "
        "global export with complete commercial facilities."
    ),
}

COPY = {
    "es": {
        "catalog": "Catálogo de Vitolas",
        "house": "Colección de la Casa",
        "adult": "Solo para compradores adultos.",
        "headers": ["Vitola", "Formato", "Fortaleza"],
        "captions": ["Caja abierta", "Presentación", "Puro suelto"],
        "tasting": "Notas de cata",
        "format": "Formato",
        "wrapper": "Capa",
        "binder": "Capote",
        "filler": "Liga / Tripa",
        "strength": "Fortaleza",
        "contact": "Contacto",
        "whatsapp": "WhatsApp: +1 809-464-5016",
        "pricing": "Precios mayorista bajo solicitud.",
        "web": "Más detalles en www.cazadordesuenocigars.com",
    },
    "en": {
        "catalog": "Vitola Catalog",
        "house": "The House Collection",
        "adult": "For adult buyers only.",
        "headers": ["Vitola", "Format", "Strength"],
        "captions": ["Open box", "Presentation", "Single cigar"],
        "tasting": "Tasting notes",
        "format": "Format",
        "wrapper": "Wrapper",
        "binder": "Binder",
        "filler": "Filler",
        "strength": "Strength",
        "contact": "Contact",
        "whatsapp": "WhatsApp: +1 809-464-5016",
        "pricing": "Wholesale pricing upon request.",
        "web": "More details at www.cazadordesuenocigars.com",
    },
}

VITOLAS = [
    {
        "name": {"es": "El Emperador", "en": "The Emperor"},
        "photos": [
            "img/el-emperador-caja-abierta.jpg",
            "img/el-emperador-caja-cerrada.jpg",
            "img/el-emperador-cigarro.jpg",
        ],
        "format": {"es": "Gran Toro 58 × 6″", "en": "Gran Toro 58 × 6″"},
        "wrapper": {"es": "San Andrés Madura (México)", "en": "San Andrés Maduro (Mexico)"},
        "binder": {"es": "Olor Dominicano", "en": "Olor Dominicano"},
        "filler": {
            "es": "Selección Premium (República Dominicana y otros)",
            "en": "Premium Selection (Dominican Republic and others)",
        },
        "strength": {"es": "Medio-fuerte", "en": "Medium-full"},
        "note": {
            "es": "Fortaleza medio-fuerte. Cacao cremoso, cedro y roble, especias suaves de canela y nuez moscada, café tostado y un final de cuero con almendra e higo.",
            "en": "Medium-full. Creamy cocoa, cedar and oak, soft spices of cinnamon and nutmeg, roasted coffee, and a finish of leather with almond and fig.",
        },
    },
    {
        "name": {"es": "Puro Habano", "en": "Puro Habano"},
        "photos": [
            "img/puro-habano-caja-abierta.jpg",
            "img/puro-habano-caja-cerrada.jpg",
            "img/puro-habano-cigarro.jpg",
        ],
        "format": {"es": "Churchill 48 × 7″", "en": "Churchill 48 × 7″"},
        "wrapper": {"es": "Habana", "en": "Habana"},
        "binder": {"es": "Olor Dominicano", "en": "Olor Dominicano"},
        "filler": {"es": "Tripa Yamazá (Criollo 98)", "en": "Yamazá filler (Criollo 98)"},
        "strength": {"es": "Fuerte", "en": "Full"},
        "note": {
            "es": "Fortaleza fuerte. Madera tostada y especias de capa Habana, cuero y cacao, con el dulzor meloso de la tripa Yamazá.",
            "en": "Full. Toasted wood and Habana-wrapper spice, leather and cocoa, with the molasses sweetness of the Yamazá filler.",
        },
    },
    {
        "name": {"es": "El Exquisito", "en": "The Exquisite"},
        "photos": [
            "img/el-exquisito-caja-abierta.jpg",
            "img/el-exquisito-caja-cerrada.jpg",
            "img/el-exquisito-cigarro.jpg",
        ],
        "format": {"es": "Gran Toro 58 × 6″", "en": "Gran Toro 58 × 6″"},
        "wrapper": {"es": "San Andrés Madura (México)", "en": "San Andrés Maduro (Mexico)"},
        "binder": {
            "es": "Doble capote (Nicaragua y Camerún)",
            "en": "Double binder (Nicaragua and Cameroon)",
        },
        "filler": {
            "es": "Selección Premium (San José de las Matas)",
            "en": "Premium Selection (San José de las Matas)",
        },
        "strength": {"es": "Fuerte", "en": "Full"},
        "note": {
            "es": "Fortaleza fuerte. Tierra húmeda y madera ahumada, cuero, café y especia de Camerún, con cierre de cacao amargo y frutos secos tostados.",
            "en": "Full. Damp earth and smoked wood, leather, coffee and Cameroon spice, closing on bitter cocoa and toasted dried fruit.",
        },
    },
    {
        "name": {"es": "El Rango", "en": "The Range"},
        "photos": [
            "img/el-rango-caja-abierta.jpg",
            "img/el-rango-caja-cerrada.jpg",
            "img/el-rango-cigarro.jpg",
        ],
        "format": {"es": "Doble Perfecto 60 × 4½″", "en": "Double Perfecto 60 × 4½″"},
        "wrapper": {"es": "San Andrés", "en": "San Andrés"},
        "binder": {"es": "Selección Premium (Nicaragua)", "en": "Premium Selection (Nicaragua)"},
        "filler": {"es": "100% Nicaragua", "en": "100% Nicaragua"},
        "strength": {"es": "Medio-fuerte", "en": "Medium-full"},
        "note": {
            "es": "Fortaleza medio-fuerte. Pimienta rica y suave, madera ligera, tierra y frutos secos, con retrogusto de especias dulces y maderas tostadas.",
            "en": "Medium-full. Rich, smooth pepper, light wood, earth and dried fruit, with a finish of sweet spice and toasted wood.",
        },
    },
    {
        "name": {"es": "Ligero 007", "en": "Ligero 007"},
        "photos": [
            "images/ligero-007/caja-abierta.jpg",
            "images/ligero-007/caja-cerrada.jpg",
            "images/ligero-007/cigarro.jpg",
        ],
        "format": {"es": "Toro 58 × 5″", "en": "Toro 58 × 5″"},
        "wrapper": {"es": "San Andrés Madura (México)", "en": "San Andrés Maduro (Mexico)"},
        "binder": {"es": "Camerún", "en": "Cameroon"},
        "filler": {
            "es": "Selección Premium (Nicaragua y otros 4 países)",
            "en": "Premium Selection (Nicaragua and 4 other countries)",
        },
        "strength": {"es": "Alta y sofisticada", "en": "High and sophisticated"},
        "note": {
            "es": "Fortaleza alta y sofisticada. Pimienta fina, roble y cedro, cacao amargo, café y avellana, con final de cuero y especias exóticas.",
            "en": "High and sophisticated. Fine pepper, oak and cedar, bitter cocoa, coffee and hazelnut, finishing on leather and exotic spice.",
        },
    },
    {
        "name": {"es": "El Sultán", "en": "The Sultan"},
        "photos": [
            "img/el-sultan-caja-abierta.jpg",
            "img/el-sultan-caja-cerrada.jpg",
            "img/el-sultan-cigarro.jpg",
        ],
        "format": {"es": "Robusto 50 × 5″", "en": "Robusto 50 × 5″"},
        "wrapper": {"es": "San Andrés", "en": "San Andrés"},
        "binder": {"es": "Olor Dominicano", "en": "Olor Dominicano"},
        "filler": {"es": "Selección Premium (Valle del Cibao)", "en": "Premium Selection (Cibao Valley)"},
        "strength": {"es": "Fuerte", "en": "Full"},
        "note": {
            "es": "Fortaleza fuerte. Pimienta negra, roble y cedro, café expreso y cuero, con cierre de cacao oscuro y tierra seca.",
            "en": "Full. Black pepper, oak and cedar, espresso and leather, closing on dark cocoa and dry earth.",
        },
    },
]


def register_fonts():
    pdfmetrics.registerFont(TTFont("Catalog", str(FONT_DIR / "georgia.ttf")))
    pdfmetrics.registerFont(TTFont("Catalog-Bold", str(FONT_DIR / "georgiab.ttf")))
    pdfmetrics.registerFont(TTFont("Catalog-Italic", str(FONT_DIR / "georgiai.ttf")))
    pdfmetrics.registerFontFamily(
        "Catalog",
        normal="Catalog",
        bold="Catalog-Bold",
        italic="Catalog-Italic",
        boldItalic="Catalog-Bold",
    )


def styles():
    return {
        "coverTitle": ParagraphStyle(
            "coverTitle",
            fontName="Catalog",
            fontSize=26,
            leading=32,
            textColor=GOLD,
            alignment=TA_CENTER,
        ),
        "coverSub": ParagraphStyle(
            "coverSub",
            fontName="Catalog",
            fontSize=12,
            leading=16,
            textColor=HexColor("#E7D7B0"),
            alignment=TA_CENTER,
        ),
        "welcome": ParagraphStyle(
            "welcome",
            fontName="Catalog-Italic",
            fontSize=11,
            leading=16,
            textColor=HexColor("#F4EFE4"),
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "section",
            fontName="Catalog",
            fontSize=18,
            leading=22,
            textColor=GOLD_DEEP,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "vitola": ParagraphStyle(
            "vitola",
            fontName="Catalog",
            fontSize=22,
            leading=26,
            textColor=GOLD_DEEP,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "caption": ParagraphStyle(
            "caption",
            fontName="Catalog",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "spec": ParagraphStyle(
            "spec",
            fontName="Catalog",
            fontSize=11,
            leading=16,
            textColor=INK,
            alignment=TA_LEFT,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Catalog",
            fontSize=12,
            leading=16,
            textColor=GOLD_DEEP,
            alignment=TA_LEFT,
        ),
        "note": ParagraphStyle(
            "note",
            fontName="Catalog",
            fontSize=11.5,
            leading=17,
            textColor=INK,
            alignment=TA_LEFT,
        ),
        "cell": ParagraphStyle(
            "cell",
            fontName="Catalog",
            fontSize=10,
            leading=13,
            textColor=INK,
        ),
        "head": ParagraphStyle(
            "head",
            fontName="Catalog-Bold",
            fontSize=10,
            leading=13,
            textColor=GOLD,
        ),
        "contactTitle": ParagraphStyle(
            "contactTitle",
            fontName="Catalog",
            fontSize=22,
            leading=28,
            textColor=GOLD,
            alignment=TA_CENTER,
        ),
        "contactBody": ParagraphStyle(
            "contactBody",
            fontName="Catalog",
            fontSize=12,
            leading=18,
            textColor=HexColor("#F4EFE4"),
            alignment=TA_CENTER,
        ),
    }


def paint_dark(canvas, doc, lang):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(HexColor("#8A93A3"))
    canvas.setFont("Catalog", 8)
    canvas.drawCentredString(A4[0] / 2, 14 * mm, COPY[lang]["adult"])
    canvas.restoreState()


def paint_light(canvas, doc, lang):
    canvas.saveState()
    canvas.setFillColor(CREAM)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.9)
    inset = 9 * mm
    canvas.rect(inset, inset, A4[0] - 2 * inset, A4[1] - 2 * inset, fill=0, stroke=1)
    canvas.setFillColor(MUTED)
    canvas.setFont("Catalog", 8)
    canvas.drawCentredString(A4[0] / 2, 12 * mm, COPY[lang]["adult"])
    canvas.restoreState()


def prepare_photo(src, dest, max_px=900):
    image = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    image.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    image.save(dest, format="JPEG", quality=84, optimize=True)


def photo_block(vitola, lang, styles_map, tmp_dir, width):
    column = width / 3
    pad = 1.5 * mm
    box_width = column - 2 * pad
    box_height = box_width * 2 / 3
    images = []
    captions = []
    for index, relative in enumerate(vitola["photos"]):
        source = REPO / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        dest = Path(tmp_dir) / f"{lang}-{vitola['name']['en'].replace(' ', '-')}-{index}.jpg"
        prepare_photo(source, dest)
        with Image.open(dest) as prepared:
            ratio = prepared.width / prepared.height
        if ratio >= 1.5:
            draw_width = box_width
            draw_height = box_width / ratio
        else:
            draw_height = box_height
            draw_width = box_height * ratio
        images.append(FlowImage(str(dest), width=draw_width, height=draw_height))
        captions.append(Paragraph(COPY[lang]["captions"][index], styles_map["caption"]))
    table = Table([images, captions], colWidths=[column, column, column])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), pad),
                ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 3),
            ]
        )
    )
    return table


def build(lang):
    copy = COPY[lang]
    sheet = styles()
    out = ROOT / f"CazadorDeSuenos_Wholesale_{lang.upper()}.pdf"
    doc = BaseDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Cazador de Sueños — {copy['catalog']}",
        author="Cazador de Sueños Cigar SRL",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates(
        [
            PageTemplate(id="dark", frames=[frame], onPage=lambda c, d: paint_dark(c, d, lang)),
            PageTemplate(id="light", frames=[frame], onPage=lambda c, d: paint_light(c, d, lang)),
        ]
    )

    story = [
        Spacer(1, 48 * mm),
        Paragraph(copy["catalog"], sheet["coverTitle"]),
        Spacer(1, 3 * mm),
        Paragraph("Cazador de Sueños Cigar SRL", sheet["coverSub"]),
        Spacer(1, 12 * mm),
        Paragraph(WELCOME[lang], sheet["welcome"]),
        NextPageTemplate("light"),
        PageBreak(),
        Paragraph(copy["house"], sheet["section"]),
        Spacer(1, 6 * mm),
    ]

    header = [Paragraph(text, sheet["head"]) for text in copy["headers"]]
    rows = [header]
    for vitola in VITOLAS:
        rows.append(
            [
                Paragraph(vitola["name"][lang], sheet["cell"]),
                Paragraph(vitola["format"][lang], sheet["cell"]),
                Paragraph(vitola["strength"][lang], sheet["cell"]),
            ]
        )
    table = Table(rows, colWidths=[58 * mm, 78 * mm, 42 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), GOLD),
                ("BACKGROUND", (0, 1), (-1, -1), white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.4, GOLD),
            ]
        )
    )
    story.append(table)

    labels = {
        "format": copy["format"],
        "wrapper": copy["wrapper"],
        "binder": copy["binder"],
        "filler": copy["filler"],
        "strength": copy["strength"],
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        for vitola in VITOLAS:
            story.append(PageBreak())
            story.append(Paragraph(vitola["name"][lang], sheet["vitola"]))
            story.append(Spacer(1, 3 * mm))
            story.append(photo_block(vitola, lang, sheet, tmp_dir, doc.width))
            story.append(Spacer(1, 6 * mm))
            for key in ("format", "wrapper", "binder", "filler", "strength"):
                story.append(Paragraph(f"<b>{labels[key]}:</b>  {vitola[key][lang]}", sheet["spec"]))
            story.append(Spacer(1, 5 * mm))
            story.append(Paragraph(copy["tasting"], sheet["label"]))
            story.append(Spacer(1, 1.5 * mm))
            story.append(Paragraph(vitola["note"][lang], sheet["note"]))

        story.extend(
            [
                NextPageTemplate("dark"),
                PageBreak(),
                Spacer(1, 58 * mm),
                Paragraph(copy["contact"], sheet["contactTitle"]),
                Spacer(1, 6 * mm),
                Paragraph(copy["whatsapp"], sheet["contactBody"]),
                Paragraph(copy["pricing"], sheet["contactBody"]),
                Spacer(1, 4 * mm),
                Paragraph(copy["web"], sheet["contactBody"]),
            ]
        )
        doc.build(story)
    return out


def main():
    register_fonts()
    for lang in ("es", "en"):
        path = build(lang)
        print(path)


if __name__ == "__main__":
    main()
