# -*- coding: utf-8 -*-
"""
توليد ملف PDF لتصريح «أجير» — مطابق للنموذج الرسمي المرفق.

يعتمد على doclayout.build() للحصول على قائمة العناصر بإحداثيات مقيسة
(1000pt عرض الصفحة)، ثم يرسمها بـ fpdf2 مع تشكيل عربي عبر HarfBuzz.
نفس العناصر تُستخدم في صفحة الطباعة (SVG) لضمان تطابق المعاينة والـ PDF.
"""
import io
import os

from fpdf import FPDF
from fpdf.enums import TextMode

import doclayout as L

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, 'static', 'img')

BOLD_STROKE_DIV = 30.0     # تسمين اصطناعي: عرض الخط = الحجم / 30


def _rgb(hexcolor):
    h = hexcolor.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class _Doc(FPDF):
    def __init__(self, w, h):
        super().__init__(orientation='P', unit='pt', format=(w, h))
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)
        self.c_margin = 0.0
        self.add_page()
        self.add_font('NK', '', L.FONT_PATH)
        self.set_text_shaping(True)

    def draw_rect(self, x, y, w, h, fill=None, stroke=None, lw=0.0):
        style = ('F' if fill else '') + ('D' if stroke else '')
        if not style:
            return
        if fill:
            self.set_fill_color(*_rgb(fill))
        if stroke:
            self.set_draw_color(*_rgb(stroke))
            self.set_line_width(lw)
        self.rect(x, y, w, h, style=style)

    def draw_text(self, x, y, s, size, bold=False, color=L.INK):
        """يرسم النص بحيث تكون الحافة اليسرى لمربع التقدّم عند x وخط الأساس عند y.

        fpdf2 يضع خط الأساس داخل الخلية عند  y_cell + h/2 + 0.3*size.
        """
        self.set_font('NK', '', size)
        col = _rgb(color)
        self.set_text_color(*col)
        if bold:
            self.set_draw_color(*col)
            self.set_line_width(size / BOLD_STROKE_DIV)
            self.text_mode = TextMode.FILL_STROKE
        else:
            self.text_mode = TextMode.FILL
        h = size * 1.2
        adv = L.metrics(s, size)[0]
        self.set_xy(x, y - 0.5 * h - 0.3 * size)
        self.cell(w=max(adv, 0.1) + 2.0, h=h, text=s, align='L')
        self.text_mode = TextMode.FILL


def build_pdf(contract, qr_png_bytes=None, verify_domain=None, footer_url=None):
    doc = L.build(contract, verify_domain=verify_domain, footer_url=footer_url)
    pdf = _Doc(doc['w'], doc['h'])
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, doc['w'], doc['h'], style='F')

    for it in doc['items']:
        t = it['t']
        if t == 'rect':
            pdf.draw_rect(it['x'], it['y'], it['w'], it['h'],
                          it.get('fill'), it.get('stroke'), it.get('lw') or 0)
        elif t == 'ellipse':
            pdf.set_fill_color(*_rgb(it.get('fill') or L.INK))
            pdf.ellipse(it['x'], it['y'], it['w'], it['h'], style='F')
        elif t == 'img':
            src = it['src']
            if src == 'qr' or src.startswith('data:'):
                if qr_png_bytes:
                    pdf.image(io.BytesIO(qr_png_bytes), x=it['x'], y=it['y'],
                              w=it['w'], h=it['h'])
            else:
                path = os.path.join(BASE_DIR, 'static', src)
                if os.path.exists(path):
                    pdf.image(path, x=it['x'], y=it['y'], w=it['w'], h=it['h'])
        elif t == 'text':
            pdf.draw_text(it['pen'], it['y'], it['s'], it['size'],
                          it['bold'], it['color'])
            if it.get('href'):
                # منطقة قابلة للنقر فوق رابط التحقق في التذييل
                adv = L.metrics(it['s'], it['size'])[0]
                pdf.link(it['pen'], it['y'] - it['size'] * 0.95,
                         max(adv, 1.0), it['size'] * 1.35, it['href'])

    return bytes(pdf.output())
