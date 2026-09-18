"""Genera el PDF de prototipos con el mismo diseño que 05_visualizador_comparativo.html.

Replica el estilo oscuro del HTML (fondo #090d16, tarjetas #151d2f, acento #38bdf8)
y produce un PDF horizontal multipágina listo para enviar.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PROTO = ROOT / "prototipos"

# ------- Paleta idéntica al HTML -------
BG = (9, 13, 22)            # #090d16
CARD = (21, 29, 47)         # #151d2f
CARD_INFO = (13, 20, 36)    # #0d1424
BORDER = (35, 50, 77)       # #23324d
ACCENT = (56, 189, 248)     # #38bdf8
TEXT = (241, 245, 249)      # #f1f5f9
MUTED = (148, 163, 184)     # #94a3b8
SUCCESS = (34, 197, 94)     # #22c55e
DANGER = (239, 68, 68)      # #ef4444

PAGE_W, PAGE_H = 1754, 1240   # A4 horizontal @ ~150 dpi
MARGIN = 64

IMG_DIR = PROTO


def load_font(size, bold=False):
    names = []
    if bold:
        names += [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"]
    names += [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"]
    for n in names:
        if Path(n).exists():
            try:
                return ImageFont.truetype(n, size)
            except Exception:
                pass
    return ImageFont.load_default()


F_H1 = load_font(46, bold=True)
F_SUB = load_font(24)
F_PILL = load_font(22, bold=True)
F_CARD_T = load_font(28, bold=True)
F_CARD_S = load_font(20)
F_ROW = load_font(21)
F_TAG = load_font(20, bold=True)
F_FOOT = load_font(20)


def new_page():
    im = Image.new("RGB", (PAGE_W, PAGE_H), BG)
    return im, ImageDraw.Draw(im)


def rounded(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if draw.textlength(probe, font=font) <= max_w:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_image(path, box_w, box_h):
    im = Image.open(path)
    if im.mode != "RGB":
        im = im.convert("RGB")
    r = min(box_w / im.width, box_h / im.height)
    return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)


def text_center(draw, cx, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)
    return w


def draw_pill(draw, x, y, text, color):
    tw = draw.textlength(text, font=F_PILL)
    pad_x, pad_y = 16, 9
    box = [x, y, x + tw + pad_x * 2, y + F_PILL.size + pad_y * 2]
    rounded(draw, box, (box[3] - box[1]) // 2, fill=CARD, outline=color, width=2)
    draw.text((x + pad_x, y + pad_y), text, font=F_PILL, fill=color)
    return box[2] - box[0]


def draw_card(page, draw, x, y, w, h, title, subtitle, img_file, rows, tag_text, tag_ok):
    rounded(draw, [x, y, x + w, y + h], 16, fill=CARD, outline=BORDER, width=2)

    draw.text((x + 22, y + 18), title, font=F_CARD_T, fill=TEXT)
    draw.text((x + 22, y + 18 + F_CARD_T.size + 8), subtitle, font=F_CARD_S, fill=MUTED)
    draw.line([(x + 1, y + 92), (x + w - 1, y + 92)], fill=BORDER, width=2)

    img_area_top = y + 96
    img_area_h = h - 96 - 150
    src = IMG_DIR / img_file
    if src.exists():
        img = fit_image(src, w - 40, img_area_h - 16)
        page.paste(img, (x + (w - img.width) // 2, img_area_top + (img_area_h - img.height) // 2))

    info_top = y + h - 148
    rounded(draw, [x + 2, info_top, x + w - 2, y + h - 2], 14, fill=CARD_INFO)

    ry = info_top + 14
    label_x = x + 22
    value_x = x + 200
    for label, value, color in rows:
        draw.text((label_x, ry), label + ":", font=F_ROW, fill=MUTED)
        draw.text((value_x, ry), value, font=F_ROW, fill=color or TEXT)
        ry += F_ROW.size + 8

    pill_col = SUCCESS if tag_ok else DANGER
    tw = draw.textlength(tag_text, font=F_TAG)
    box = [x + 22, ry + 4, x + 22 + tw + 28, ry + 4 + F_TAG.size + 14]
    rounded(draw, box, 6, fill=(30, 41, 59), outline=pill_col, width=2)
    draw.text((x + 36, ry + 11), tag_text, font=F_TAG, fill=pill_col)


def build_pages():
    cards = [
        {
            "title": "1. Original con Barra PRM",
            "subtitle": "Captura con logo inferior y barra negra",
            "img": "01_original_muestra.jpg",
            "rows": [
                ("Estado", "CON BLOQUE PRM", DANGER),
                ("Dimensiones", "960 x 1280 px", None),
                ("Defecto", "Texto PRM + Barra Windows", None),
            ],
            "tag": "CON BLOQUE PRM",
            "tag_ok": False,
        },
        {
            "title": "2. Recorte Automático",
            "subtitle": "Eliminación precisa de la franja PRM",
            "img": "02_recorte_automatico_prm.jpg",
            "rows": [
                ("Estado", "LIMPIO / OK", SUCCESS),
                ("Dimensiones", "960 x 1004 px", None),
                ("Protección facial", "Barbilla intacta (+144px)", None),
            ],
            "tag": "LIMPIO / OK",
            "tag_ok": True,
        },
        {
            "title": "3. Formato Cédula (3:4)",
            "subtitle": "Relación de aspecto estándar para credenciales",
            "img": "03_recorte_formato_cedula_3x4.jpg",
            "rows": [
                ("Relación", "3:4 (Retrato Oficial)", None),
                ("Dimensiones", "753 x 1004 px", None),
                ("Centrado", "Sujeto centrado automáticamente", None),
            ],
            "tag": "FORMATO 3:4",
            "tag_ok": True,
        },
        {
            "title": "4. Formato Cuadrado (1:1)",
            "subtitle": "Relación de aspecto para avatar / sistemas web",
            "img": "04_recorte_cuadrado_1x1.jpg",
            "rows": [
                ("Relación", "1:1 (Avatar / Web)", None),
                ("Dimensiones", "960 x 960 px", None),
                ("Enfoque", "Rostro y hombros optimizados", None),
            ],
            "tag": "FORMATO 1:1",
            "tag_ok": True,
        },
    ]

    pages = []
    per_page = 2
    for start in range(0, len(cards), per_page):
        page, d = new_page()
        y = MARGIN

        if start == 0:
            text_center(d, PAGE_W / 2, y, "Padrón Electoral — Auditoría de Recorte",
                        F_H1, ACCENT)
            y += F_H1.size + 14
            text_center(d, PAGE_W / 2, y,
                        "Comparativa visual de prototipos generados por el pipeline determinista con Face Safety Gate.",
                        F_SUB, MUTED)
            y += F_SUB.size + 22

            pills = [
                ("100% Sin Inpainting", SUCCESS),
                ("Face Safety Gate", ACCENT),
                ("Cero Deformación Facial", SUCCESS),
            ]
            widths = [d.textlength(p[0], font=F_PILL) + 32 for p in pills]
            gap = 18
            total = sum(widths) + gap * (len(pills) - 1)
            px = (PAGE_W - total) / 2
            for (t, c), w in zip(pills, widths):
                draw_pill(d, px, y, t, c)
                px += w + gap
            y += F_PILL.size + 34
        else:
            text_center(d, PAGE_W / 2, y, "Padrón Electoral — Auditoría de Recorte",
                        F_H1, ACCENT)
            y += F_H1.size + 30

        chunk = cards[start:start + per_page]
        card_w = (PAGE_W - MARGIN * 2 - 34) // 2
        card_h = PAGE_H - y - MARGIN - 40
        for i, c in enumerate(chunk):
            x = MARGIN + i * (card_w + 34)
            draw_card(page, d, x, y, card_w, card_h, c["title"], c["subtitle"],
                      c["img"], c["rows"], c["tag"], c["tag_ok"])

        text_center(d, PAGE_W / 2, PAGE_H - MARGIN + 4,
                    "Proyecto Padrón Crop • Procesamiento masivo en CPU • 100% Local y Privado",
                    F_FOOT, MUTED)
        pages.append(page)

    return pages


def main():
    pages = build_pages()
    out_pdf = PROTO / "Prototipos_Padron_Crop.pdf"
    pages[0].save(out_pdf, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    print(f"PDF generado: {out_pdf}  ({out_pdf.stat().st_size/1024:.0f} KB, {len(pages)} páginas)")

    for i, p in enumerate(pages, 1):
        jpg = PROTO / f"Prototipos_Padron_{i}.jpg"
        p.save(jpg, "JPEG", quality=88, optimize=True, progressive=True)
        print(f"Imagen WhatsApp: {jpg}  ({jpg.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
