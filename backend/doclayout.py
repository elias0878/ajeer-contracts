# -*- coding: utf-8 -*-
"""
محرّك تخطيط وثيقة «تصريح أجير» — نسخة مطابقة للنموذج الرسمي المرفق.

كل الأرقام (نقاط، أصل الإحداثيات أعلى يسار الصفحة، عرض الصفحة = 1000pt)
مأخوذة بالقياس البكسلي من ملفَّي التصريح الرسميين:
    SIRAJ AHMED ALI ASGHAR.pdf           (1000 × 1524.66 pt)
    SAAD SHAFIQUE MUHAMMAD SHAFIQUE.pdf  (1000 × 1549.84 pt)

المخرَج: قائمة عناصر رسم (rect / ellipse / img / text) تُستخدم من:
    * pdfdoc.build_pdf()          → ملف PDF (fpdf2 + HarfBuzz)
    * templates/contract_doc.html → صفحة الطباعة (عناصر مطلقة بنفس الإحداثيات)
وبذلك تكون المعاينة والـ PDF متطابقتين تماماً.

نوع الخط في النموذج الرسمي: Noto Kufi Arabic. الحروف العريضة فيه تسمين
اصطناعي (synthetic bold) بنفس مقاييس الوزن 400، لذا نرسمها بوضع FILL_STROKE
بعرض خط = الحجم/30.
"""
import os

import uharfbuzz as hb
from fontTools.ttLib import TTFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, 'static', 'fonts', 'NotoKufi-Regular.ttf')

# --------------------------------------------------------------------------
#  هندسة الصفحة والقيم المقيسة
# --------------------------------------------------------------------------
PAGE_W = 1000.0
BASE_PAGE_H = 1524.66           # ارتفاع التصريح المرجعي
BASE_TABLE_BOTTOM = 929.7
BOTTOM_GAP = BASE_PAGE_H - BASE_TABLE_BOTTOM    # 594.96

INK = '#000000'
FILL = '#e7ecef'
BORDER = '#d1d4db'
HDR_BORDER = '#c6c6c6'
LINK = '#1b5cba'
DEFAULT_FOOTER_URL = 'https://ajeer.qiwa.sa/verify/'   # الموقع الرسمي للتحقق

# الترويسة
HDR = (105.0, 88.15, 943.3, 212.4)
HDR_LW = 0.55
QR_RECT = (187.31, 100.25, 79.75, 82.37)
SERIAL_CX, SERIAL_INK_TOP, SERIAL_SIZE = 223.8, 195.17, 14.66
TITLE_INK_RIGHT, TITLE_INK_TOP, TITLE_SIZE = 500.52, 134.84, 17.2
LOGO_AJEER = (604.41, 111.23, 84.47, 70.30)
LOGO_MLSD = (742.92, 118.05, 183.63, 56.66)

# المقدمة
INTRO_RIGHT, INTRO_SIZE = 942.29, 14.0
INTRO_INK_TOPS = (270.72, 306.40, 344.18)

# الجدول
COLS = (106.0, 313.2, 522.0, 731.4, 941.8)
TABLE_TOP = 388.0        # مركز حدّ الجدول العلوي
CELL_LW = 1.55           # سماكة حدّ الخلية
CELL_GAP = 0.5           # الفراغ بين حدّي خليتين متجاورتين
ROW_H = 44.72            # ارتفاع صف من سطر واحد (بين مركزَي حدّين)
ROW_H_FIRST = 43.80      # الصف الأول (حدّ أعلى مفرد)
ROW_H_LAST = 43.80       # الصف الأخير (حدّ أسفل مفرد)
ROW_LINE_EXTRA = 26.13   # الزيادة في ارتفاع الصف لكل سطر إضافي
CELL_LINE_H = 27.81      # تباعد الأسطر داخل الخلية
CELL_SIZE = 13.6
CELL_PAD = 9.5
CELL_BASE = 28.05        # خط الأساس للسطر الأول من مركز الحدّ العلوي
SEC_BASE = 27.20         # خط أساس عناوين الأقسام
# ارتفاع الصفحة = أسفل الجدول + المساحة السفلية. المطابقة التامة للنموذجين
# المرجعيين (1524.66 و1549.84pt) تعطي: المساحة السفلية تتناقص 0.03636pt
# لكل نقطة يطول فيها الجدول (نفس نسبة النموذج الرسمي).
PAGE_TAIL_AT = (930.47, 594.32)
PAGE_TAIL_SLOPE = -0.03636

DECL_SIZE, DECL_INK_TOP = 15.8, 27.67
PROMISE_SIZE, PROMISE_INK_TOP = 16.8, 75.68
BULLET_SIZE = 13.6
BULLET_INK_TOPS = (121.60, 160.70, 199.50, 238.60, 277.40)
BULLET_TEXT_RIGHT = 905.04
BULLET_DOT = (915.01, 6.82, 7.87, 3.14)     # x, w, h, إزاحة y عن أعلى حبر السطر
FOOT_SIZE = 13.7
FOOT_FROM_BOTTOM = 164.74    # من أعلى حبر السطر الأول إلى أسفل الصفحة
FOOT2_DY = 30.43             # بين سطري التذييل
FOOT1_CX, FOOT2_CX = 523.35, 524.40

# --------------------------------------------------------------------------
#  نصوص ثابتة (كما في النموذج الرسمي)
# --------------------------------------------------------------------------
INTRO_LINES = (
    'نشعركم أنه تم التعاقد من قبلنا كجهة مقدمة للخدمة مع الجهة المستفيدة من الخدمة حسب المعلومات المبينة أدناه، ولذلك تم تسجيل',
    'معلومات العقد لتكون بحوزة العامل لإثبات عدم مخالفته لنظام العمل ولتقديمها إلى من يهمه الأمر من الجهات المختصة عند طلبها للتحقق من',
    'صحة تواجده في مكان تقديم الخدمة.',
)
TITLE_TEXT = 'تصريح أجير - تعاقد أجير'
DECL_TEXT = 'أقرارات'
PROMISE_TEXT = 'أقر أنا المنشأة المقدمة للخدمة والموضحة بياناتي أعلاه وأتعهد ب :'
BULLETS = (
    'إن العامل حامل هذا التصريح يقر بأن البيانات المدونة فيه صحيحة على مسؤوليته.',
    'يعمل لدى المنشأة المستفيدة بموجب عقد الخدمة المسجّل ولا يجوز له العمل بخلاف ذلك.',
    'الالتزام والامتثال لأنظمة العمل واللوائح والقرارات ذات العلاقة.',
    'أن الموقع الإلكتروني هو المرجع الأساسي، وأي تعديل أو كشط في هذا التصريح يجعله غير قانوني.',
    'للتحقق من صحة هذا التصريح بإمكانك زيارة موقع أجير.',
)
FOOT1_AR = 'للتحقق من صحة هذا التصريح وسريان مفعوله بإمكانك زيارة موقع أجير'
FOOT2 = 'خدمة معتمدة من وزارة الموارد البشرية والتنمية الاجتماعية'
LBL_ORG_NO = 'رقم المنشأة في وزارة الموارد البشرية والتنمية الاجتماعية'


# --------------------------------------------------------------------------
#  قياس النص (HarfBuzz) — نفس مسار التشكيل المستخدم في PDF
# --------------------------------------------------------------------------
_blob = _hbfont = _tt = _glyf = _order = None
_upem = 1000


def _init():
    global _blob, _hbfont, _tt, _glyf, _order, _upem
    if _hbfont is not None:
        return
    _blob = hb.Blob.from_file_path(FONT_PATH)
    _hbfont = hb.Font(hb.Face(_blob))
    _tt = TTFont(FONT_PATH)
    _glyf = _tt['glyf']
    _order = _tt.getGlyphOrder()
    _upem = _tt['head'].unitsPerEm


def _shape(txt):
    _init()
    buf = hb.Buffer()
    buf.add_str(txt)
    buf.guess_segment_properties()
    hb.shape(_hbfont, buf, {'kern': True, 'liga': True, 'calt': True})
    return buf


def metrics(txt, size):
    """(advance, ink_xmin, ink_xmax, ink_ymax, ink_ymin) بالـ points."""
    buf = _shape(txt)
    up = _upem / float(size)
    adv = sum(p.x_advance for p in buf.glyph_positions) / up
    xmin, xmax, ymax, ymin = 1e9, -1e9, -1e9, 1e9
    x = 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        gl = _glyf[_order[info.codepoint]]
        if gl.numberOfContours != 0:
            gx = x + pos.x_offset
            xmin = min(xmin, (gx + gl.xMin) / up)
            xmax = max(xmax, (gx + gl.xMax) / up)
            ymax = max(ymax, gl.yMax / up)
            ymin = min(ymin, gl.yMin / up)
        x += pos.x_advance
    if xmin > xmax:
        return adv, 0.0, adv, 0.0, 0.0
    return adv, xmin, xmax, ymax, ymin


def ascender(txt, size):
    return metrics(txt, size)[3]


def wrap(txt, size, maxw):
    words = str(txt or '').split()
    if not words:
        return ['']
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + ' ' + w
        if metrics(trial, size)[0] <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


# --------------------------------------------------------------------------
#  بناء العناصر
# --------------------------------------------------------------------------
def _rect(items, x, y, w, h, fill=None, stroke=None, lw=0.0):
    items.append({'t': 'rect', 'x': round(x, 2), 'y': round(y, 2), 'w': round(w, 2),
                  'h': round(h, 2), 'fill': fill, 'stroke': stroke, 'lw': round(lw, 3)})


def _text(items, anchor, x, baseline, s, size, bold=False, color=INK, href=None):
    if not str(s or '').strip():
        return
    it = {'t': 'text', 'anchor': anchor, 'x': round(x, 3), 'y': round(baseline, 3),
          's': str(s), 'size': round(size, 2), 'bold': bool(bold), 'color': color}
    if href:
        it['href'] = href
    items.append(it)


def _text_top(items, anchor, x, ink_top, s, size, bold=False, color=INK):
    """يضع النص بحيث يكون أعلى حبره عند ink_top."""
    _text(items, anchor, x, ink_top + ascender(str(s), size), s, size, bold, color)


_AR = set(range(0x0600, 0x0700)) | set(range(0xFB50, 0xFEFF))


def direction_of(txt):
    for ch in txt:
        o = ord(ch)
        if o in _AR:
            return 'rtl'
        if ch.isalpha():
            return 'ltr'
    return 'rtl'


def _resolve(items):
    """يحوّل محاور النص إلى موضع قلم + عرض التقدّم + الاتجاه (يستخدمه العارضان)."""
    for it in items:
        if it['t'] != 'text':
            continue
        s, size, a = it['s'], it['size'], it['anchor']
        adv, xmin, xmax, _, _ = metrics(s, size)
        x = it['x']
        if a == 'l':
            pen = x
        elif a == 'r':
            pen = x - adv
        elif a == 'c':
            pen = x - adv / 2.0
        elif a == 'lk':
            pen = x - xmin
        elif a == 'rk':
            pen = x - xmax
        elif a == 'ck':
            pen = x - (xmin + xmax) / 2.0
        else:
            pen = x
        it['pen'] = round(pen, 3)
        it['adv'] = round(adv, 3)
        it['dir'] = direction_of(s)
    return items


def build(c, qr_src=None, verify_domain=None, footer_url=None):
    """يبني عناصر الوثيقة. c: بيانات التعاقد (dict)."""
    items = []
    vals = {k: (c.get(k) or '') for k in (
        'worker_name', 'profession', 'id_no', 'nationality', 'provider_name',
        'provider_no', 'beneficiary_name', 'beneficiary_no', 'description',
        'start_date', 'end_date', 'site')}

    # ---------------- الترويسة ----------------
    x0, y0, x1, y1 = HDR
    _rect(items, x0, y0, x1 - x0, y1 - y0, fill='#ffffff', stroke=HDR_BORDER, lw=HDR_LW)

    qx, qy, qw, qh = QR_RECT
    items.append({'t': 'img', 'x': qx, 'y': qy, 'w': qw, 'h': qh, 'src': qr_src or 'qr'})

    _text_top(items, 'ck', SERIAL_CX, SERIAL_INK_TOP, c.get('permit_no', ''), SERIAL_SIZE, True)
    _text_top(items, 'rk', TITLE_INK_RIGHT, TITLE_INK_TOP, TITLE_TEXT, TITLE_SIZE, True)

    for rect, name in ((LOGO_AJEER, 'img/permit-ajeer.png'), (LOGO_MLSD, 'img/permit-mlsd.png')):
        items.append({'t': 'img', 'x': rect[0], 'y': rect[1], 'w': rect[2], 'h': rect[3], 'src': name})

    # ---------------- المقدّمة ----------------
    for line, top in zip(INTRO_LINES, INTRO_INK_TOPS):
        _text_top(items, 'rk', INTRO_RIGHT, top, line, INTRO_SIZE)

    # ---------------- الجدول ----------------
    rows = [
        ('sec', 'بيانات العامل'),
        ('row4', [vals['profession'], 'المهنة', vals['worker_name'], 'اسم العامل']),
        ('row4', [vals['nationality'], 'الجنسية', vals['id_no'], 'رقم الهوية / الإقامة']),
        ('sec', 'بيانات مقدم الخدمة'),
        ('row4', [vals['provider_no'], LBL_ORG_NO, vals['provider_name'], 'المنشأة المقدمة للخدمة']),
        ('sec', 'بيانات المستفيد من الخدمة'),
        ('row4', [vals['beneficiary_no'], LBL_ORG_NO, vals['beneficiary_name'],
                  'المنشأة المستفيدة من الخدمة']),
        ('sec', 'بيانات التصريح'),
        ('wide', [vals['description'], 'نبذة عن التعاقد']),
        ('row4', [vals['end_date'], 'التاريخ نهاية التصريح', vals['start_date'],
                  'التاريخ بداية التصريح']),
        ('wide', [vals['site'], 'مواقع العمل']),
    ]

    laid = []
    for kind, payload in rows:
        if kind == 'sec':
            laid.append({'kind': 'sec', 'text': payload, 'lines': 1, 'cells': []})
            continue
        cells = []
        if kind == 'row4':
            for i, txt in enumerate(payload):
                maxw = COLS[i + 1] - COLS[i] - 2 * (CELL_LW + CELL_PAD)
                cells.append({'col': i, 'span': 1, 'text': txt,
                              'lines': wrap(txt, CELL_SIZE, maxw)})
        else:
            maxw = COLS[3] - COLS[0] - 2 * (CELL_LW + CELL_PAD)
            cells.append({'col': 0, 'span': 3, 'text': payload[0],
                          'lines': wrap(payload[0], CELL_SIZE, maxw)})
            maxw = COLS[4] - COLS[3] - 2 * (CELL_LW + CELL_PAD)
            cells.append({'col': 3, 'span': 1, 'text': payload[1],
                          'lines': wrap(payload[1], CELL_SIZE, maxw)})
        n = max(len(cl['lines']) for cl in cells)
        laid.append({'kind': kind, 'cells': cells, 'lines': max(n, 1)})

    last_i = len(laid) - 1
    tops = [TABLE_TOP]
    for i, r in enumerate(laid):
        if i == 0:
            h = ROW_H_FIRST
        elif i == last_i:
            h = ROW_H_LAST
        else:
            h = ROW_H
        h += (r['lines'] - 1) * ROW_LINE_EXTRA
        tops.append(tops[-1] + h)
    table_bottom = tops[-1]

    # التظليل (داخل حدود الخلية)
    half = (CELL_LW + CELL_GAP) / 2.0        # 1.025
    for ri, r in enumerate(laid):
        ya, yb = tops[ri], tops[ri + 1]
        spans = [(COLS[0], COLS[4])] if r['kind'] == 'sec' else [
            (COLS[cl['col']], COLS[cl['col'] + cl['span']]) for cl in r['cells']
            if cl['col'] in (1, 3)]
        for fx0, fx1 in spans:
            _rect(items, fx0 + CELL_LW, ya + CELL_LW, fx1 - fx0 - 2 * CELL_LW,
                  yb - ya - 2 * CELL_LW, fill=FILL)

    # الحدود: كل خلية بإطار 1.55pt؛ الحدود الخارجية خطّ واحد، والفواصل
    # بين خليتين متجاورتين خطّان متوازيان بفراغ 0.5pt (كما في النموذج).
    last = len(laid) - 1
    for ri, r in enumerate(laid):
        ya, yb = tops[ri], tops[ri + 1]
        first_row, last_row = (ri == 0), (ri == last)
        if r['kind'] == 'sec':
            segs = [[0, 4]]
        else:
            segs, cur = [], None
            for cl in sorted(r['cells'], key=lambda z: z['col']):
                a, b = cl['col'], cl['col'] + cl['span']
                if cur and a == cur[1]:
                    cur[1] = b
                else:
                    cur = [a, b]
                    segs.append(cur)

        top_bars = [(ya - CELL_LW / 2.0,)] if first_row else [
            (ya - CELL_LW - CELL_GAP / 2.0,), (ya + CELL_GAP / 2.0,)]
        bot_bars = [(yb - CELL_LW / 2.0,)] if last_row else [
            (yb - CELL_LW - CELL_GAP / 2.0,), (yb + CELL_GAP / 2.0,)]
        vtop = ya + (0 if first_row else CELL_GAP / 2.0)
        vbot = yb - (0 if last_row else CELL_GAP / 2.0)
        for a, b in segs:
            xa, xb = COLS[a], COLS[b]
            for (ybg,) in top_bars:
                _rect(items, xa, ybg, xb - xa, CELL_LW, fill=BORDER)
            for (ybg,) in bot_bars:
                _rect(items, xa, ybg, xb - xa, CELL_LW, fill=BORDER)
            lx = xa - CELL_LW if a == 0 else xa - CELL_LW - CELL_GAP / 2.0
            rx = (xb - CELL_LW) if b == 4 else (xb + CELL_GAP / 2.0)
            _rect(items, lx, vtop, CELL_LW, vbot - vtop, fill=BORDER)
            _rect(items, rx, vtop, CELL_LW, vbot - vtop, fill=BORDER)

    # نصوص الخلايا
    for ri, r in enumerate(laid):
        base0 = tops[ri] + (SEC_BASE if r['kind'] == 'sec' else CELL_BASE)
        if r['kind'] == 'sec':
            _text(items, 'c', (COLS[0] + COLS[4]) / 2.0, base0, r['text'], CELL_SIZE, True)
            continue
        for cl in r['cells']:
            right = COLS[cl['col'] + cl['span']] - CELL_LW - CELL_PAD
            for i, line in enumerate(cl['lines']):
                _text(items, 'r', right, base0 + i * CELL_LINE_H, line, CELL_SIZE)

    # ---------------- الإقرارات ----------------
    T = table_bottom
    cx = (COLS[0] + COLS[4]) / 2.0
    _text_top(items, 'ck', 524.14, T + DECL_INK_TOP, DECL_TEXT, DECL_SIZE, True)
    _text_top(items, 'rk', INTRO_RIGHT, T + PROMISE_INK_TOP, PROMISE_TEXT, PROMISE_SIZE, True)
    for txt, top in zip(BULLETS, BULLET_INK_TOPS):
        ink = T + top
        _text_top(items, 'rk', BULLET_TEXT_RIGHT, ink, txt, BULLET_SIZE)
        dx, dw, dh, dy = BULLET_DOT
        items.append({'t': 'ellipse', 'x': dx, 'y': round(ink + dy, 2), 'w': dw, 'h': dh,
                      'fill': INK})

    # ---------------- التذييل (مثبّت من أسفل الصفحة) ----------------
    page_h = round(T + PAGE_TAIL_AT[1] + PAGE_TAIL_SLOPE * (T - PAGE_TAIL_AT[0]), 2)
    domain = (footer_url or verify_domain or DEFAULT_FOOTER_URL).strip()
    if not domain.endswith('/'):
        domain += '/'
    link = '(%s)' % domain
    ar_adv = metrics(FOOT1_AR, FOOT_SIZE)[0]
    ln_adv = metrics(link, FOOT_SIZE)[0]
    sp_adv = metrics(' ', FOOT_SIZE)[0]
    total = ar_adv + sp_adv + ln_adv
    left = FOOT1_CX - total / 2.0
    foot1_top = page_h - FOOT_FROM_BOTTOM
    baseline = foot1_top + ascender(FOOT1_AR, FOOT_SIZE)
    _text(items, 'l', left, baseline, link, FOOT_SIZE, False, LINK, href=domain)
    _text(items, 'r', left + total, baseline, FOOT1_AR, FOOT_SIZE)
    _rect(items, left, baseline + 2.45, ln_adv, 0.85, fill=LINK)
    _text_top(items, 'ck', FOOT2_CX, foot1_top + FOOT2_DY, FOOT2, FOOT_SIZE)

    _resolve(items)
    return {'w': PAGE_W, 'h': page_h,
            'items': items, 'table_bottom': round(table_bottom, 2)}


def page_height(c):
    return build(c)['h']
