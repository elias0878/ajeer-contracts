# -*- coding: utf-8 -*-
"""
مُولّد مستند «تعاقد أجير» — fpdf2 + HarfBuzz (تشكيل عربي صحيح، بايثون خالص).

كل الإحداثيات مأخوذة بالقياس من النموذج الرسمي (Letter = 612×792 نقطة)،
وتُستخدم نفس الأرقام في قالب المتصفح (CSS) لضمان تطابق تام بين المعاينة والـ PDF.
"""
import io
import os

from fpdf import FPDF
from PIL import ImageFont

_SCALE = 40
_FONT_FILES = {
    '': 'Almarai-Regular.ttf',
    'B': 'Almarai-Bold.ttf',
    'L': 'Almarai-Light.ttf',
}
_pil_cache = {}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, 'static', 'fonts')
LOGO_PATH = os.path.join(BASE_DIR, 'static', 'img', 'ajeer_logo.png')

PAGE_W, PAGE_H = 612.0, 792.0

BORDER = (217, 221, 226)
FILL = (236, 240, 241)
INK = (43, 43, 43)
INK_SOFT = (51, 51, 51)
INK_HEAD = (17, 17, 17)

# ------------------------------------------------------------------
#  هندسة المستند (نفس أرقام النموذج الرسمي — تم قياسها من الملف المرفق)
# ------------------------------------------------------------------
HDR = dict(x0=59.5, y0=27.8, x1=565.5, y1=107.4)
QR = dict(x0=69.5, y0=29.9, w=59.1, h=49.5)
LOGO = dict(x0=406.0, y0=50.0, w=157.0, h=36.0)

TABLE = dict(x0=58.1, x1=567.4,
             rows=[185.3, 207.8, 226.1, 243.8, 266.9, 295.2, 318.2, 346.1, 369.1, 386.9, 405.1, 422.9])

INTRO_LINES = [
    ('نشعركم أنه تم التعاقد من قبلنا كجهة مقدمة للخدمة مع الجهة المستفيدة من الخدمة حسب المعلومات المبينة أدناه، ولذلك تم تسجيل', 132.0),
    ('معلومات العقد لتكون بحوزة العامل لإثبات عدم مخالفته لنظام العمل ولتقديمها إلى من يهمه الأمر من الجهات المختصة عند طلبها', 147.4),
    ('للتحقق من صحة تواجده في مكان تقديم الخدمة', 161.0),
]

PROMISE = ('أقر أنا المنشأة المقدمة للخدمة والموضحة بياناتي أعلاه وأتعهد بـ:', 457.0)

BULLETS = [
    [('إن العامل حامل هذا التصريح بحمله له يقر ويتعهد بأن البيانات المدونة فيه صحيحة على مسؤوليته الشخصية، وأنه يعمل لدى المنشأة', 474.2),
     ('ولحسابها، بموجب رخصة إقامة سارية المفعول. وأتحمل أي تبعات قانونية أو غرامات تترتب على خلاف المذكور أعلاه.', 488.7)],
    [('الالتزام والتقيّد بأنظمة العمل والعمال وأي أنظمة ولوائح وقرارات أخرى ذات علاقة.', 504.2)],
    [('أن الموقع الإلكتروني الخاص بأجير أو القائمين عليه عبارة عن وسيط إلكتروني ما بين الباحثين عن العمل وأصحاب الأعمال فقط وبدون', 519.7),
     ('أي التزام قانوني أو غيره على القائمين على موقع أجير.', 534.7)],
    [('أي تعديل أو كشف في هذا التصريح يجعله لاغياً.', 549.7)],
]

FOOTER = [
    ('للتحقق من صحة هذا التصريح وسريان مفعوله بإمكانك زيارة موقع أجير ({domain})', 745.8),
    ('* خدمة معتمدة من وزارة الموارد البشرية والتنمية الاجتماعية *', 757.3),
]


class Doc(FPDF):
    def __init__(self):
        super().__init__(orientation='P', unit='pt', format=(PAGE_W, PAGE_H))
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)
        self.add_page()
        self.add_font('Almarai', '', os.path.join(FONT_DIR, 'Almarai-Regular.ttf'))
        self.add_font('Almarai', 'B', os.path.join(FONT_DIR, 'Almarai-Bold.ttf'))
        self.add_font('AlmaraiLight', '', os.path.join(FONT_DIR, 'Almarai-Light.ttf'))
        self.set_text_shaping(True)

    # ---- أدوات ----
    def tw(self, txt, size, style=''):
        self.set_font('Almarai' if style != 'L' else 'AlmaraiLight', '' if style == 'L' else style, size)
        return self.get_string_width(txt)

    @staticmethod
    def _pil(txt, size, style=''):
        key = (style, round(size, 2))
        f = _pil_cache.get(key)
        if f is None:
            f = ImageFont.truetype(os.path.join(FONT_DIR, _FONT_FILES[style]), int(size * _SCALE))
            _pil_cache[key] = f
        try:
            bb = f.getbbox(txt)
            asc = f.getmetrics()[0]
        except Exception:
            return 0.0
        return (bb[1] - asc) / _SCALE      # إزاحة أعلى الحبر عن خط الأساس (سالبة)

    def _draw(self, x, ink_top, txt, size, style='', color=INK, align='left', width=None):
        """يرسم نصاً بـ cell() (تشكيل عربي صحيح) مع ضبط دقيق لموضع الحبر."""
        font = 'Almarai' if style != 'L' else 'AlmaraiLight'
        fstyle = '' if style == 'L' else style
        self.set_font(font, fstyle, size)
        self.set_text_color(*color)
        w = self.get_string_width(txt) if width is None else width
        y = ink_top + self._pil(txt, size, style) + 0.3827 * size
        if align == 'right':
            x = x - w
        elif align == 'center':
            x = x - w / 2.0
        self.set_xy(x, y)
        self.cell(w=max(w, 1.0), h=size * 1.5, text=txt, align='L')
        return w

    def write_right(self, x_right, ink_top, txt, size, style='', color=INK):
        if not txt:
            return 0.0
        return self._draw(x_right, ink_top, txt, size, style, color, 'right')

    def write_center(self, x_center, ink_top, txt, size, style='', color=INK):
        if not txt:
            return 0.0
        return self._draw(x_center, ink_top, txt, size, style, color, 'center')

    def fit(self, txt, size, maxw, style=''):
        """تصغير الخط تدريجياً حتى يتسع النص في العرض."""
        s = size
        while s > 6.4 and self.tw(txt, s, style) > maxw:
            s -= 0.15
        return s

    def wrap(self, txt, size, maxw, style=''):
        words = str(txt).split()
        lines, cur = [], ''
        for w in words:
            trial = (cur + ' ' + w).strip()
            if not cur or self.tw(trial, size, style) <= maxw:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or ['']


def _cell(pdf, x_right, x_left, top, bottom, text, style='', size=8.5, pad=None, color=INK, align='right', dy=0.0):
    text = (text or '').strip()
    if not text:
        return
    if pad is None:
        pad = 4.6
    maxw = (x_right - x_left) - pad - 3.0
    lines = pdf.wrap(text, size, maxw, style) if pdf.tw(text, size, style) > maxw else [text]
    if len(lines) > 2:
        lines = [lines[0], ' '.join(lines[1:])]
        while pdf.tw(lines[1], size, style) > maxw and ' ' in lines[1]:
            lines[1] = lines[1].rsplit(' ', 1)[0]
    lh = size * 1.38
    block = lh * len(lines)
    first = (top + bottom) / 2.0 - block / 2.0 + (lh - size) / 2.0 + dy
    for i, ln in enumerate(lines):
        if align == 'center':
            pdf.write_center((x_right + x_left) / 2.0, first + i * lh, ln, size, style, color)
        else:
            pdf.write_right(x_right - pad, first + i * lh, ln, size, style, color)


def build_pdf(contract, qr_png_bytes=None):
    pdf = Doc()

    # ================= الترويسة =================
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.7)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(HDR['x0'], HDR['y0'], HDR['x1'] - HDR['x0'], HDR['y1'] - HDR['y0'], style='DF')

    if qr_png_bytes:
        pdf.image(io.BytesIO(qr_png_bytes), x=QR['x0'], y=QR['y0'], w=QR['w'], h=QR['h'])
    if os.path.exists(LOGO_PATH):
        pdf.image(LOGO_PATH, x=LOGO['x0'], y=LOGO['y0'], w=LOGO['w'], h=LOGO['h'])

    pdf.write_center(292.5, 63.3, 'تعاقد اجير', 12.4, 'B', INK_HEAD)
    pdf.write_center(99.0, 86.3, contract.get('permit_no', ''), 10.5, '', INK_SOFT)
    pdf.write_center(99.0, 99.1, 'امسح للتحقق', 6.6, '', (76, 76, 76))

    # ================= المقدمة =================
    for line, top in INTRO_LINES:
        pdf.write_right(565.5, top + 3.0, line, 9.2, '', INK)

    # ================= الجدول =================
    t = TABLE
    rows = t['rows']
    colw = (t['x1'] - t['x0']) / 4.0
    cols = [t['x1'] - i * colw for i in range(5)]   # يمين ← يسار

    # تعبئة الأقسام
    pdf.set_fill_color(*FILL)
    for si in (0, 3, 5, 7):
        pdf.rect(t['x0'], rows[si], t['x1'] - t['x0'], rows[si + 1] - rows[si], style='F')

    # تعبئة أعمدة العناوين
    filled = [(1, 1), (1, 3), (2, 1), (2, 3), (4, 1), (4, 3), (6, 1), (6, 3),
              (8, 1), (8, 3), (9, 1), (10, 1)]
    for r, ci in filled:
        pdf.rect(cols[ci + 1], rows[r], cols[ci] - cols[ci + 1], rows[r + 1] - rows[r], style='F')

    # الشبكة
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.7)
    for y in rows:
        pdf.line(t['x0'], y, t['x1'], y)
    for x in cols:
        pdf.line(x, rows[0], x, rows[-1])

    lbl_pad, val_pad, last_pad = 4.6, 2.4, 8.3
    lbl_dy, val_dy = 2.6, 0.4

    def section(row, text):
        _cell(pdf, cols[0], cols[4], rows[row], rows[row + 1], text, 'B', 8.9, pad=0, align='center')

    # --- بيانات العامل ---
    section(0, 'بيانات العامل')
    _cell(pdf, cols[0], cols[1], rows[1], rows[2], 'اسم العامل', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[1], cols[2], rows[1], rows[2], contract.get('worker_name'), pad=val_pad)
    _cell(pdf, cols[2], cols[3], rows[1], rows[2], 'المهنة', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[3], cols[4], rows[1], rows[2], contract.get('nationality'), pad=last_pad)

    _cell(pdf, cols[0], cols[1], rows[2], rows[3], 'رقم الهوية / الإقامة', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[1], cols[2], rows[2], rows[3], contract.get('id_no'), pad=val_pad)
    _cell(pdf, cols[2], cols[3], rows[2], rows[3], 'الجنسية', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[3], cols[4], rows[2], rows[3], contract.get('profession'), pad=last_pad)

    # --- مقدم الخدمة ---
    section(3, 'بيانات مقدم الخدمة')
    _cell(pdf, cols[0], cols[1], rows[4], rows[5], 'المنشأة المقدمة للخدمة', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[1], cols[2], rows[4], rows[5], contract.get('provider_name'), pad=val_pad)
    _cell(pdf, cols[2], cols[3], rows[4], rows[5], 'رقم المنشأة في وزارة الموارد البشرية والتنمية الاجتماعية', pad=lbl_pad)
    _cell(pdf, cols[3], cols[4], rows[4], rows[5], contract.get('provider_no'), pad=last_pad)

    # --- المستفيد ---
    section(5, 'بيانات المستفيد من الخدمة')
    _cell(pdf, cols[0], cols[1], rows[6], rows[7], 'المنشأة المستفيدة من الخدمة', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[1], cols[2], rows[6], rows[7], contract.get('beneficiary_name'), pad=val_pad)
    _cell(pdf, cols[2], cols[3], rows[6], rows[7], 'رقم المنشأة في وزارة الموارد البشرية والتنمية الاجتماعية', pad=lbl_pad)
    _cell(pdf, cols[3], cols[4], rows[6], rows[7], contract.get('beneficiary_no'), pad=last_pad)

    # --- التصريح ---
    section(7, 'بيانات التصريح')
    _cell(pdf, cols[0], cols[1], rows[8], rows[9], 'تاريخ بداية التصريح', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[1], cols[2], rows[8], rows[9], contract.get('start_date'), pad=val_pad)
    _cell(pdf, cols[2], cols[3], rows[8], rows[9], 'تاريخ نهاية التصريح', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[3], cols[4], rows[8], rows[9], contract.get('end_date'), pad=last_pad)

    _cell(pdf, cols[0], cols[1], rows[9], rows[10], 'نبذة عن التعاقد', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[1], cols[4], rows[9], rows[10], contract.get('description'), pad=val_pad)

    _cell(pdf, cols[0], cols[1], rows[10], rows[11], 'مواقع العمل', pad=lbl_pad, dy=lbl_dy)
    _cell(pdf, cols[1], cols[4], rows[10], rows[11], contract.get('site'), pad=val_pad)

    # ================= الإقرارات =================
    pdf.write_center(313.1, 431.7, 'إقرارات', 9.3, 'B', INK_HEAD)
    pdf.write_right(561.5, PROMISE[1], PROMISE[0], 9.0, 'B', INK_HEAD)

    for group in BULLETS:
        for i, (line, top) in enumerate(group):
            if i == 0:
                pdf.set_fill_color(*INK)
                pdf.ellipse(556.6, top + 4.0, 2.5, 2.5, style='F')
                pdf.write_right(551.5, top, line, 9.4, '', INK)
            else:
                pdf.write_right(561.5, top, line, 9.4, '', INK)

    # ================= التذييل =================
    domain = contract.get('verify_domain') or 'https://ajeer.com.sa'
    pdf.write_center(311.5, FOOTER[0][1], FOOTER[0][0].format(domain=domain), 9.2, '', INK_SOFT)
    pdf.write_center(311.5, FOOTER[1][1], FOOTER[1][0], 9.2, '', INK_SOFT)

    out = pdf.output()
    return bytes(out)
