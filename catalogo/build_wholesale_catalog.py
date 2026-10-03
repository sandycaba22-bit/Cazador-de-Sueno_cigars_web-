"""Genera los catálogos mayoristas ES y EN con notas de cata condensadas."""

from pathlib import Path

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
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
FONT_DIR = Path(r"C:\Windows\Fonts")

IVORY = HexColor("#F6F1E7")
INK = HexColor("#1C1612")
MUTED = HexColor("#5C5348")
GOLD = HexColor("#8C6A2F")
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
        "catalog": "Catálogo mayorista",
        "house": "Colección de la casa",
        "adult": "Solo para compradores adultos.",
        "headers": ["Vitola", "Formato", "Fortaleza"],
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
        "catalog": "Wholesale catalog",
        "house": "The house collection",
        "adult": "For adult buyers only.",
        "headers": ["Vitola", "Format", "Strength"],
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


def styles():
    return {
        "brand": ParagraphStyle(
            "brand",
            fontName="Catalog",
            fontSize=28,
            leading=34,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "kicker": ParagraphStyle(
            "kicker",
            fontName="Catalog",
            fontSize=11,
            leading=15,
            textColor=GOLD,
            alignment=TA_CENTER,
            tracking=1.2,
        ),
        "welcome": ParagraphStyle(
            "welcome",
            fontName="Catalog-Italic",
            fontSize=12,
            leading=18,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "section",
            fontName="Catalog",
            fontSize=18,
            leading=22,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "coverTitle": ParagraphStyle(
            "coverTitle",
            fontName="Catalog",
            fontSize=18,
            leading=22,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "vitola": ParagraphStyle(
            "vitola",
            fontName="Catalog",
            fontSize=26,
            leading=30,
            textColor=INK,
            spaceAfter=6,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Catalog-Bold",
            fontSize=11,
            leading=16,
            textColor=GOLD,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Catalog",
            fontSize=12,
            leading=18,
            textColor=INK,
        ),
        "note": ParagraphStyle(
            "note",
            fontName="Catalog",
            fontSize=12.5,
            leading=19,
            textColor=INK,
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
            textColor=white,
        ),
        "center": ParagraphStyle(
            "center",
            fontName="Catalog",
            fontSize=12,
            leading=18,
            textColor=INK,
            alignment=TA_CENTER,
        ),
    }


def paint_page(canvas, doc, lang):
    canvas.saveState()
    canvas.setFillColor(IVORY)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, A4[1] - 8, A4[0], 8, fill=1, stroke=0)
    canvas.setFillColor(MUTED)
    canvas.setFont("Catalog", 8)
    copy = COPY[lang]
    canvas.drawString(18 * mm, 12 * mm, copy["adult"])
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"{doc.page}")
    canvas.restoreState()


def build(lang):
    copy = COPY[lang]
    s = styles()
    out = ROOT / f"CazadorDeSuenos_Wholesale_{lang.upper()}.pdf"
    doc = BaseDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Cazador de Sueños — {copy['catalog']}",
        author="Cazador de Sueños Cigar SRL",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates(
        [PageTemplate(id="main", frames=[frame], onPage=lambda c, d: paint_page(c, d, lang))]
    )

    story = [
        Spacer(1, 42 * mm),
        Paragraph("Cazador de Sueños", s["brand"]),
        Paragraph("Cigar SRL · República Dominicana", s["kicker"]),
        Spacer(1, 8 * mm),
        Paragraph(copy["catalog"], s["coverTitle"]),
        Spacer(1, 6 * mm),
        Paragraph(WELCOME[lang], s["welcome"]),
        Spacer(1, 10 * mm),
        Paragraph(copy["adult"], s["center"]),
        NextPageTemplate("main"),
        PageBreak(),
        Paragraph(copy["house"], s["section"]),
        Spacer(1, 4 * mm),
    ]

    header = [Paragraph(text, s["head"]) for text in copy["headers"]]
    rows = [header]
    for vitola in VITOLAS:
        rows.append(
            [
                Paragraph(vitola["name"][lang], s["cell"]),
                Paragraph(vitola["format"][lang], s["cell"]),
                Paragraph(vitola["strength"][lang], s["cell"]),
            ]
        )
    table = Table(rows, colWidths=[58 * mm, 72 * mm, 44 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("BACKGROUND", (0, 1), (-1, -1), white),
                ("FONTNAME", (0, 0), (-1, 0), "Catalog-Bold"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, LINE),
                ("BOX", (0, 0), (-1, -1), 0.6, GOLD),
            ]
        )
    )
    story.append(table)

    fields = ("format", "wrapper", "binder", "filler", "strength")
    labels = {
        "format": copy["format"],
        "wrapper": copy["wrapper"],
        "binder": copy["binder"],
        "filler": copy["filler"],
        "strength": copy["strength"],
    }
    for vitola in VITOLAS:
        story.append(PageBreak())
        story.append(Paragraph(vitola["name"][lang], s["vitola"]))
        for key in fields:
            story.append(Paragraph(f"{labels[key]}: {vitola[key][lang]}", s["body"]))
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(copy["tasting"], s["label"]))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(vitola["note"][lang], s["note"]))

    story.extend(
        [
            PageBreak(),
            Paragraph(copy["contact"], s["vitola"]),
            Paragraph(copy["whatsapp"], s["body"]),
            Spacer(1, 3 * mm),
            Paragraph(copy["pricing"], s["body"]),
            Paragraph(copy["web"], s["body"]),
            Spacer(1, 8 * mm),
            Paragraph(copy["adult"], s["body"]),
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
