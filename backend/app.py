# -*- coding: utf-8 -*-
"""
منصة إدارة وإنشاء العقود — تعاقد أجير
Flask app (Vercel-ready, Supabase / SQLite)
مع نظام حسابات وصلاحيات وسجل نشاط على نمط لوحة «بلدي».
"""
import base64
import io
import os
import secrets
import random
import re
import string
import time
from datetime import date, datetime, timedelta, timezone

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, url_for)

import auth
import authstore as store
from auth import (account_expired, can, can_any, can_manage_target, current_user,
                  deny, display_name, ensure_bootstrap, is_owner, is_self,
                  log_audit, login_required, permission_required, permissions)
import doclayout
from db import FIELDS, get_db
from pdfdoc import build_pdf
from permissions import (CATEGORIES, PERMISSION_CATALOG, PERMISSION_KEYS,
                         PERMISSION_MAP, ROLE_LABELS, ROLE_PRESETS,
                         catalog_by_category)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = os.environ.get('SECRET_KEY', 'ajeer-contracts-2026-secret')
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

PUBLIC_BASE = (os.environ.get('PUBLIC_BASE_URL') or '').rstrip('/')


# ---------------------------------------------------------------- helpers
def settings():
    return get_db().get_settings()


def gen_permit_no():
    for _ in range(60):
        no = 'TQ' + ''.join(random.choices(string.digits, k=9))
        if not get_db().permit_exists(no):
            return no
    return 'TQ' + str(int(datetime.now().timestamp()))[-9:]


def qr_bytes(text):
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=0)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def qr_data_uri(text):
    return 'data:image/png;base64,' + base64.b64encode(qr_bytes(text)).decode()


def _host_base():
    """النطاق الفعلي الذي يفتح منه المستخدم المنصة (يتكيّف تلقائياً مع أي نطاق مربوط)."""
    try:
        host = request.host.split(':')[0].lower()
    except RuntimeError:
        return ''
    if not host or host in ('localhost', '127.0.0.1') or host.endswith('.local') \
            or host.startswith('192.168.') or host.startswith('10.'):
        return ''
    return request.host_url.rstrip('/')


def base_url():
    return _host_base() or PUBLIC_BASE or request.url_root.rstrip('/')


PUBLIC_LANDING_PATH = '/l'
# كل زيارة بلا مسار أو لمسار غير موجود/غير صحيح تُحوَّل إلى الموقع الرسمي مباشرة
# دون عرض أي صفحة أو تفاصيل على المنصة.
OFFICIAL_HOME_URL = 'https://ajeer.qiwa.sa/'


def official_redirect():
    """تحويل فوري إلى الموقع الرسمي بصفحة فارغة تماماً (لا يُعرض أي محتوى)."""
    resp = redirect(OFFICIAL_HOME_URL)
    resp.data = b''
    resp.headers['Content-Length'] = '0'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def public_base(s=None):
    """النطاق العام (Canonical): من الإعدادات أولاً ثم نطاق الطلب الحالي."""
    s = s or settings()
    return (s.get('verify_domain') or _host_base() or DEFAULT_VERIFY_DOMAIN
            or PUBLIC_BASE or request.url_root).rstrip('/')


HIJRI_EPOCH = 579  # 622 م - 43 فرق التقويمين ≈ 579


def hijri_year(d=None):
    """تقدير تقريبي للسنة الهجرية (يكفي لعرض حقوق النشر)."""
    d = d or date.today()
    jd = (d.year * 365.25) + ((datetime(d.year, d.month, d.day) - datetime(d.year, 1, 1)).days)
    return int((jd - 1948084) / 354.367) + 1 if False else int((d.year - 622) * 1.0307) + 1


DEFAULT_VERIFY_DOMAIN = ''          # فارغ = نطاق التطبيق الحالي
OFFICIAL_VERIFY_URL = 'https://ajeer.qiwa.sa/verify/'   # الموقع الرسمي (رابط التذييل)
DEFAULT_VERIFY_PATH = '/verify/'   # مطابق لمسار الموقع الرسمي: ajeer.qiwa.sa/verify/


def new_verify_token():
    """رمز تحقق عشوائي غير قابل للتخمين (64 محرفاً base64url)."""
    return secrets.token_urlsafe(48)


def verify_base(s=None):
    """أساس رابط التحقق: النطاق + المسار، مثل https://<domain>/verify/"""
    s = s or settings()
    # النطاق المثبّت في الإعدادات (Canonical) يتقدّم؛ وإلا يتبع النطاق الذي تُفتح به المنصة
    domain = public_base(s)
    path = (s.get('verify_path') or DEFAULT_VERIFY_PATH).strip()
    if path and not path.startswith('/'):
        path = '/' + path
    if path.endswith('index.php') or path.endswith('index.html'):
        # روابط قديمة على شكل /agiar/index.php → /agiar/
        path = path.rsplit('/', 1)[0] + '/'
    return domain + path


def verify_link(contract_or_permit, token=None, s=None):
    """رابط التحقق المفرد لكل تعاقد: <base>?id=<token>"""
    s = s or settings()
    if isinstance(contract_or_permit, dict):
        tok = contract_or_permit.get('verify_token') or token
    else:
        tok = token
    return f'{verify_base(s)}?id={tok}' if tok else ''


def ensure_tokens():
    """يمنح كل تعاقد قديم رمز تحقق إن لم يكن له."""
    try:
        db = get_db()
        for row in db.missing_tokens():
            db.set_token(row['id'], new_verify_token())
    except Exception:
        pass


def days_left(end_date, today=None):
    """عدد الأيام المتبقية حتى نهاية التصريح (None إذا تعذّر التحليل)."""
    if not end_date:
        return None
    today = today or date.today()
    if isinstance(end_date, str):
        try:
            end_date = datetime.strptime(end_date[:10], '%Y-%m-%d').date()
        except ValueError:
            return None
    elif isinstance(end_date, datetime):
        end_date = end_date.date()
    return (end_date - today).days


def status_of(c):
    today = date.today()
    try:
        st = datetime.strptime(c['start_date'][:10], '%Y-%m-%d').date()
        en = datetime.strptime(c['end_date'][:10], '%Y-%m-%d').date()
    except Exception:
        return ('unknown', 'غير محدد')
    if today < st:
        return ('pending', 'لم يبدأ')
    if today > en:
        return ('expired', 'منتهي')
    if (en - today).days <= 30:
        return ('soon', 'ينتهي قريباً')
    return ('active', 'ساري')


def doc_context(c, s=None):
    """سياق صفحة الطباعة/الـ PDF — يضم تخطيط الوثيقة الجاهز (doclayout)."""
    s = s or settings()
    ctx = dict(c)
    ctx['qr'] = qr_data_uri(verify_link(c, s=s))
    ctx['verify_domain'] = s.get('verify_domain') or PUBLIC_BASE or request.url_root.rstrip('/')
    ctx['verify_url'] = verify_link(c, s=s)
    ctx['footer_url'] = (s.get('official_verify_url') or OFFICIAL_VERIFY_URL).strip()
    ctx['doc'] = doclayout.build(ctx, verify_domain=ctx['verify_domain'],
                                 footer_url=ctx['footer_url'])
    return ctx


def render_doc(c, mode, auto_print=False):
    """يعرض صفحة الطباعة (SVG بإحداثيات مقيسة) بنفس بيانات الـ PDF."""
    ctx = doc_context(c)
    return render_template('contract_doc.html', c=ctx, doc=ctx['doc'], mode=mode,
                           auto_print=auto_print, assets=url_for('static', filename=''),
                           pdf_url=url_for('pdf_contract', id_=c.get('id') or 0),
                           back_url=url_for('dashboard' if mode != 'embed' else 'dashboard'))


def validate(form):
    errors = {}
    required = {
        'permit_no': 'رقم التصريح', 'worker_name': 'اسم العامل',
        'id_no': 'رقم الهوية / الإقامة', 'profession': 'المهنة',
        'nationality': 'الجنسية', 'provider_name': 'المنشأة المقدمة للخدمة',
        'provider_no': 'رقم المنشأة المقدمة للخدمة',
        'beneficiary_name': 'المنشأة المستفيدة من الخدمة',
        'beneficiary_no': 'رقم المنشأة المستفيدة من الخدمة',
        'description': 'نبذة عن التعاقد', 'start_date': 'تاريخ بداية التصريح',
        'end_date': 'تاريخ نهاية التصريح', 'site': 'مواقع العمل',
    }
    for k, label in required.items():
        if not (form.get(k) or '').strip():
            errors[k] = f'{label} مطلوب'
    for k in ('start_date', 'end_date'):
        v = (form.get(k) or '').strip()
        if v:
            try:
                datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                errors[k] = 'صيغة التاريخ يجب أن تكون YYYY-MM-DD'
    if not errors.get('start_date') and not errors.get('end_date'):
        if form['end_date'] < form['start_date']:
            errors['end_date'] = 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية'
    if not re.match(r'^TQ\d{9}$', (form.get('permit_no') or '').strip()):
        errors['permit_no'] = 'رقم التصريح يجب أن يبدأ بـ TQ ثم 9 أرقام'
    return errors


def payload(src):
    return {k: (src.get(k) or '').strip() for k in FIELDS}


def owns(c, user=None):
    u = user or current_user()
    if not u or c.get('created_by') in (None, ''):
        return False
    return int(c['created_by']) == int(u['id'])


def can_view(c):
    return can('contracts.view_all') or (can('contracts.view_own') and owns(c))


def can_edit(c):
    return can('contracts.edit_all') or (can('contracts.edit_own') and owns(c))


def can_delete(c):
    return can('contracts.delete_all') or (can('contracts.delete_own') and owns(c))


def require_contract(id_, mode='view'):
    c = get_db().get_contract(id_)
    if not c:
        abort(404)
    ok = {'view': can_view, 'edit': can_edit, 'delete': can_delete}[mode](c)
    if not ok:
        label = {'view': 'عرض', 'edit': 'تعديل', 'delete': 'حذف'}[mode]
        abort(403) if False else None
        return None, (render_template('error.html', page='',
                                      error=f'ليست لديك صلاحية {label} هذا التعاقد',
                                      title='صلاحية غير كافية'), 403)
    return c, None


def my_contracts(q=None):
    if can('contracts.view_all'):
        return get_db().list_contracts(q)
    if can('contracts.view_own'):
        return get_db().list_contracts(q, created_by=current_user()['id'])
    return []



# ----------------------------------------------------------------------
#  اسم بديل بصيغة «نقاط»: /ajeer.qiwa.sa/...  (يُخدَم دون تحويل)
# ----------------------------------------------------------------------
DOTTED_PREFIXES = ('/ajeer.qiwa.sa', '/ajeer.qiwa')


class _DottedAlias:
    """يجعل المسارات التي تبدأ بـ /ajeer.qiwa.sa تعمل كما هي دون تغيير الرابط."""

    def __init__(self, wsgi):
        self.wsgi = wsgi

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '') or '/'
        for pre in DOTTED_PREFIXES:
            if path == pre or path.startswith(pre + '/'):
                environ['PATH_INFO'] = path[len(pre):] or '/'
                break
        return self.wsgi(environ, start_response)


app.wsgi_app = _DottedAlias(app.wsgi_app)


# ---------------------------------------------------------------- auth hooks
@app.before_request
def _before():
    if request.endpoint == 'static' or request.path.startswith('/static/'):
        return
    try:
        ensure_bootstrap()
    except Exception:
        pass
    if not getattr(app, '_tokens_checked', False):
        try:
            ensure_tokens()
            app._tokens_checked = True
        except Exception:
            pass
    auth.load_current_user()


@app.before_request
def _gate():
    """حجب كل المسارات غير العامة قبل أي معالجة."""
    if request.endpoint == 'static' or request.path.startswith('/static/'):
        return
    # أي مسار غير موجود → الموقع الرسمي مباشرة (بلا عرض أي صفحة أو تفاصيل)
    if request.endpoint is None and request.method in ('GET', 'HEAD') \
            and not request.path.startswith('/api/'):
        return official_redirect()
    blocked = auth.gate()
    if blocked is not None:
        try:
            if request.method in ('GET', 'HEAD') and not auth.current_user():
                auth.log_denied('AUTH_REQUIRED')
        except Exception:
            pass
        return blocked
    u = auth.current_user()
    if u is None and request.endpoint in auth.PUBLIC_ENDPOINTS:
        return
    return None


@app.after_request
def _security_headers(resp):
    """ترويسات أمان على كل الاستجابات."""
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Referrer-Policy', 'no-referrer')
    resp.headers.setdefault('Permissions-Policy',
                            'geolocation=(), microphone=(), camera=(), payment=()')
    resp.headers.setdefault('X-Robots-Tag', 'noindex, nofollow, noarchive, nosnippet')
    if not request.path.startswith('/static/'):
        resp.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; "
            "frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
    if request.path.startswith('/api/') or auth.current_user():
        resp.headers.setdefault('Cache-Control', 'no-store, private')
    resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return resp


@app.template_filter('dt')
def _fmt_dt(v):
    """تنسيق التواريخ بتوقيت الرياض."""
    if not v:
        return '—'
    d = auth._parse_dt(v)
    if not d:
        return str(v)[:16].replace('T', ' ')
    return d.astimezone(timezone(timedelta(hours=3))).strftime('%Y-%m-%d %H:%M')


@app.template_filter('dshort')
def _fmt_dshort(v):
    if not v:
        return ''
    d = auth._parse_dt(v)
    if not d:
        return str(v)[:10]
    return d.astimezone(timezone(timedelta(hours=3))).strftime('%Y-%m-%d')


# ---------------------------------------------------------------- audit helpers
ACTION_LABELS = {
    'auth.login': 'تسجيل دخول', 'auth.logout': 'تسجيل خروج',
    'account.update': 'تعديل بيانات الحساب', 'account.password': 'تغيير كلمة المرور',
    'contracts.create': 'إنشاء تعاقد', 'contracts.update': 'تعديل تعاقد',
    'contracts.delete': 'حذف تعاقد', 'contracts.pdf': 'تصدير PDF',
    'contracts.duplicate': 'نسخ تعاقد', 'contracts.bulk_revoke': 'إلغاء تعاقدات مستخدم',
    'contracts.bulk_delete': 'حذف تعاقدات مستخدم',
    'users.create': 'إنشاء مستخدم', 'users.update': 'تعديل مستخدم',
    'users.delete': 'حذف مستخدم', 'users.reset_password': 'إعادة تعيين كلمة المرور',
    'users.activate': 'تفعيل حساب', 'users.deactivate': 'تعطيل حساب',
    'permissions.update': 'تعديل الصلاحيات', 'settings.update': 'تعديل الإعدادات',
    'system.bootstrap': 'تهيئة النظام',
    'security.denied': 'محاولة وصول محجوبة',
    'security.throttle': 'حجب مؤقت (محاولات كثيرة)',
    'auth.login_failed': 'محاولة دخول فاشلة',
    'verify.view': 'فتح رابط تحقق',
}
DETAIL_LABELS = {
    'email': 'البريد', 'new_email': 'البريد الجديد', 'role': 'الدور',
    'permissions': 'الصلاحيات', 'permissions_added': 'صلاحيات مضافة',
    'permissions_removed': 'صلاحيات مسحوبة', 'is_active': 'نشط',
    'contract_limit': 'حد التعاقدات', 'expires_at': 'الانتهاء',
    'permit_no': 'رقم التصريح', 'worker_name': 'العامل', 'fields': 'الحقول المعدّلة',
    'before': 'القيم السابقة', 'affected': 'عدد التعاقدات', 'name': 'الاسم',
    'full_name': 'الاسم', 'from': 'من', 'note': 'ملاحظة',
    'org_name': 'اسم المنصة', 'verify_domain': 'نطاق التحقق',
    'default_provider_name': 'المقدم الافتراضي', 'default_provider_no': 'رقم المقدم',
    'default_site': 'الموقع الافتراضي',
    'ip': 'العنوان', 'ua': 'المتصفح', 'method': 'الطريقة',
    'reason': 'السبب', 'found': 'موجود', 'action': 'الإجراء',
}


def action_label(a):
    return ACTION_LABELS.get(a, a)


ENTITY_LABELS = {'user': 'مستخدم', 'contract': 'تعاقد', 'settings': 'إعدادات',
                 'permission': 'صلاحية', 'system': 'النظام', 'route': 'مسار',
                 'auth': 'دخول', 'auth_email': 'بريد محاولة دخول'}


def entity_label(e):
    return ENTITY_LABELS.get(e, e or '')


def details_pairs(d):
    """قائمة (تسمية عربية, قيمة) لعرض التفاصيل كشرائح صغيرة."""
    if not d or not isinstance(d, dict):
        return []
    out = []
    for k, v in d.items():
        if v in (None, '', [], {}):
            continue
        if isinstance(v, list):
            if k in ('permissions', 'permissions_added', 'permissions_removed'):
                v = '، '.join(PERMISSION_MAP[x]['label'] for x in v if x in PERMISSION_MAP) or '—'
            else:
                v = '، '.join(str(x) for x in v)
        elif isinstance(v, dict):
            v = '، '.join(f'{DETAIL_LABELS.get(kk, kk)}: {vv}' for kk, vv in v.items())
        elif isinstance(v, bool):
            v = 'نعم' if v else 'لا'
        else:
            sv = str(v)
            if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', sv):
                d = auth._parse_dt(sv)
                if d:
                    v = d.astimezone(timezone(timedelta(hours=3))).strftime('%Y-%m-%d')
        out.append((DETAIL_LABELS.get(k, k), str(v)))
    return out


def details_text(d):
    if not d:
        return '—'
    if not isinstance(d, dict):
        return str(d)[:160]
    parts = []
    for k, v in d.items():
        if v in (None, '', [], {}):
            continue
        if isinstance(v, list):
            if k in ('permissions', 'permissions_added', 'permissions_removed'):
                v = '، '.join(PERMISSION_MAP[x]['label'] for x in v if x in PERMISSION_MAP) or '—'
            else:
                v = '، '.join(str(x) for x in v)
        elif isinstance(v, dict):
            v = '، '.join(f'{DETAIL_LABELS.get(kk, kk)}: {vv}' for kk, vv in v.items())
        elif isinstance(v, bool):
            v = 'نعم' if v else 'لا'
        parts.append(f'{DETAIL_LABELS.get(k, k)}: {v}')
    return ' · '.join(parts)[:220] or '—'


@app.context_processor
def inject_globals():
    u = current_user()
    return dict(
        current_year=date.today().year, today=date.today(),
        me=u, can=can, can_any=can_any,
        role_label=ROLE_LABELS.get(u['role'], '') if u else '',
        me_name=display_name(u), me_initials=auth.initials(u) if u else '',
        permission_catalog=PERMISSION_CATALOG, catalog_by_category=catalog_by_category(),
        permission_map=PERMISSION_MAP, perm_count=len(permissions()),
        action_label=action_label, details_text=details_text,
        details_pairs=details_pairs, entity_label=entity_label,
        hijri_year=hijri_year,
        official_verify_url=OFFICIAL_VERIFY_URL,
    )


# ---------------------------------------------------------------- auth routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user():
        return redirect(url_for('dashboard'))
    err = None
    email = ''
    if request.method == 'POST':
        email = auth.normalize_email(request.form.get('email'))
        pw = request.form.get('password') or ''
        if not email or not pw:
            err = 'يرجى إدخال البريد الإلكتروني وكلمة المرور'
        else:
            ip = auth._client_ip()
            try:
                ip_fails = store.count_recent_failures('auth.login_failed', 'auth', ip, 15)
                mail_fails = store.count_recent_failures('auth.login_failed', 'auth_email', email, 15)
            except Exception:
                ip_fails = mail_fails = 0
            if ip_fails >= 12 or mail_fails >= 8:
                log_audit('security.throttle', 'auth', email, {'ip': ip})
                return render_template('login.html', email=email,
                                       error='محاولات دخول كثيرة فاشلة. تم الحجب مؤقتاً لمدة 15 دقيقة '
                                             'لحماية الحساب، حاول لاحقاً.'), 429
            try:
                user = store.get_user_by_email(email)
            except Exception as e:
                return render_template('login.html', error='تعذّر الوصول إلى نظام الحسابات. '
                                       'تأكد من إعداد قاعدة البيانات.', email=email), 503
            if not user or not auth.verify_password(pw, user.get('password_hash')):
                err = 'البريد الإلكتروني أو كلمة المرور غير صحيحة'
                try:
                    store.add_audit(None, 'system', 'auth.login_failed', 'auth', ip,
                                    {'email': email, 'ua': (request.headers.get('User-Agent') or '')[:120]})
                    store.add_audit(None, 'system', 'auth.login_failed', 'auth_email', email,
                                    {'ip': ip})
                except Exception:
                    pass
                time.sleep(0.35)
            elif not user.get('is_active'):
                err = 'هذا الحساب معطّل. يرجى التواصل مع مدير المنصة.'
            elif account_expired(user):
                err = 'انتهت صلاحية هذا الحساب. يرجى التواصل مع مدير المنصة.'
            else:
                token, _exp = auth.start_session(user)
                g.user = user
                g.perms = set(PERMISSION_KEYS) if is_owner(user) else set(store.get_permissions(user['id']))
                log_audit('auth.login', 'user', user['id'], {'email': email})
                nxt = request.args.get('next') or request.form.get('next')
                if not (nxt and nxt.startswith('/') and not nxt.startswith('//')):
                    nxt = url_for('dashboard')
                resp = redirect(nxt)
                auth.set_session_cookie(resp, token)
                flash(f'أهلاً بك، {display_name(user)}', 'success')
                return resp
    return render_template('login.html', error=err, email=email)


@app.route('/logout')
@app.route('/logout', methods=['POST'])
def logout():
    th = getattr(g, 'session_token', None)
    u = current_user()
    if th:
        try:
            store.delete_session(th)
        except Exception:
            pass
    if u:
        log_audit('auth.logout', 'user', u['id'], {'email': u['email']})
    resp = redirect(url_for('login'))
    auth.clear_session_cookie(resp)
    return resp


@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    u = current_user()
    errors = {}
    if request.method == 'POST':
        action = request.form.get('action') or 'profile'
        if action == 'profile':
            full_name = (request.form.get('full_name') or '').strip()
            email = auth.normalize_email(request.form.get('email'))
            if not full_name:
                errors['full_name'] = 'الاسم مطلوب'
            if not auth.is_valid_email(email):
                errors['email'] = 'صيغة البريد الإلكتروني غير صحيحة'
            dup = store.get_user_by_email(email) if email else None
            if dup and int(dup['id']) != int(u['id']):
                errors['email'] = 'البريد الإلكتروني مستخدم مسبقاً'
            if not errors:
                store.update_user(u['id'], {'full_name': full_name, 'email': email})
                log_audit('account.update', 'user', u['id'],
                          {'email': u['email'], 'new_email': email, 'name': full_name})
                flash('تم تحديث بيانات الحساب', 'success')
                return redirect(url_for('account'))
        elif action == 'password':
            cur = request.form.get('current_password') or ''
            new = request.form.get('new_password') or ''
            rep = request.form.get('confirm_password') or ''
            if not auth.verify_password(cur, u.get('password_hash')):
                errors['current_password'] = 'كلمة المرور الحالية غير صحيحة'
            if not auth.is_valid_password(new):
                errors['new_password'] = 'كلمة المرور الجديدة يجب ألا تقل عن 6 محرفاً'
            elif new != rep:
                errors['confirm_password'] = 'كلمتا المرور غير متطابقتين'
            if not errors:
                store.update_user(u['id'], {'password_hash': auth.hash_password(new)})
                log_audit('account.password', 'user', u['id'], {'email': u['email']})
                flash('تم تغيير كلمة المرور — الجلسات الأخرى أُنهيت', 'success')
                th = getattr(g, 'session_token', None)
                try:
                    store.delete_sessions_for_user(u['id'], keep_hash=th)
                except Exception:
                    pass
                return redirect(url_for('account'))
    sessions = []
    try:
        sessions = store.active_sessions_count(u['id'])
    except Exception:
        pass
    return render_template('account.html', page='account', errors=errors,
                           sessions=sessions, my_role=ROLE_LABELS.get(u['role'], ''),
                           my_perms=sorted(permissions()))


# ---------------------------------------------------------------- contracts
@app.route('/')
def root():
    """زيارة النطاق بلا مسار → الموقع الرسمي مباشرة بلا عرض أي صفحة."""
    return official_redirect()


@app.route('/l')
@app.route('/l/')
@app.route('/landing')
@app.route('/landing/')
def landing():
    """مسارات الهبوط القديمة → الموقع الرسمي (توافق مع الروابط السابقة)."""
    return official_redirect()


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    q = (request.args.get('q') or '').strip()
    st = request.args.get('status') or 'all'
    if not can_any('contracts.view_all', 'contracts.view_own'):
        return render_template('error.html', page='',
                               error='ليست لديك صلاحية عرض التعاقدات. تواصل مع مدير المنصة.',
                               title='صلاحية غير كافية'), 403
    try:
        contracts = my_contracts(q or None)
    except Exception as e:
        return render_template('error.html', page='', error=str(e)), 500
    for c in contracts:
        c['status'], c['status_label'] = status_of(c)
        c['is_mine'] = owns(c)
    stats = {
        'total': len(contracts),
        'active': sum(1 for c in contracts if c['status'] in ('active', 'soon')),
        'soon': sum(1 for c in contracts if c['status'] == 'soon'),
        'expired': sum(1 for c in contracts if c['status'] == 'expired'),
        'pending': sum(1 for c in contracts if c['status'] == 'pending'),
    }
    today = date.today()
    soon_list = []
    for c in contracts:
        if c['status'] in ('soon', 'expired'):
            left = days_left(c.get('end_date'), today)
            c['days_left'] = left
            if left is not None and -7 <= left <= 45:
                soon_list.append(c)
    soon_list.sort(key=lambda x: (x.get('days_left') if x.get('days_left') is not None else 9999))
    soon_list = soon_list[:4]
    recent = []
    if can('audit.view'):
        try:
            recent = store.list_audit(limit=6)
        except Exception:
            recent = []
    if st == 'active':
        contracts = [c for c in contracts if c['status'] in ('active', 'soon')]
    elif st != 'all':
        contracts = [c for c in contracts if c['status'] == st]
    return render_template('dashboard.html', page='dashboard', contracts=contracts,
                           stats=stats, settings=settings(), q=q, st=st,
                           soon_list=soon_list, recent=recent,
                           backend=db.backend, scope='all' if can('contracts.view_all') else 'own')


@app.route('/contracts/new', methods=['GET', 'POST'])
@permission_required('contracts.create')
def new_contract():
    u = current_user()
    if account_expired(u):
        return render_template('error.html', page='', error='انتهت صلاحية حسابك، لا يمكنك إنشاء تعاقدات جديدة',
                               title='حساب منتهي'), 403
    used = 0
    try:
        used = get_db().count_by_user(u['id'])
    except Exception:
        pass
    ok, msg = auth.certificate_quota(u, used)
    if not ok:
        return render_template('error.html', page='', error=msg, title='تجاوز الحد'), 403

    s = settings()
    db = get_db()
    if request.method == 'POST':
        data = payload(request.form)
        errors = validate(data)
        if not errors and db.permit_exists(data['permit_no']):
            errors['permit_no'] = 'رقم التصريح مستخدم مسبقاً'
        if errors:
            return render_template('form.html', page='new', c=data, errors=errors,
                                   settings=s, mode='new'), 422
        data['created_by'] = u['id']
        data['created_by_name'] = display_name(u)
        data['created_by_email'] = u['email']
        data['verify_token'] = new_verify_token()
        row = db.create_contract(data)
        log_audit('contracts.create', 'contract', row['id'],
                  {'permit_no': data['permit_no'], 'worker_name': data['worker_name']})
        flash('تم إنشاء التعاقد بنجاح — يمكنك الآن تحميل المستند', 'success')
        return redirect(url_for('view_contract', id_=row['id']))

    today = date.today()
    try:
        next_year = today.replace(year=today.year + 1)
    except ValueError:
        next_year = today.replace(year=today.year + 1, day=28)
    c = {
        'id': 0, 'permit_no': gen_permit_no(), 'worker_name': '', 'id_no': '',
        'profession': '', 'nationality': 'مصر',
        'provider_name': s['default_provider_name'], 'provider_no': s['default_provider_no'],
        'beneficiary_name': '', 'beneficiary_no': '', 'description': '',
        'start_date': today.isoformat(), 'end_date': next_year.isoformat(),
        'site': s['default_site'],
    }
    return render_template('form.html', page='new', c=c, errors={}, settings=s, mode='new',
                           quota_used=used, quota=(u.get('contract_limit')))


@app.route('/contracts/<int:id_>/edit', methods=['GET', 'POST'])
@login_required
def edit_contract(id_):
    c, err = require_contract(id_, 'edit')
    if err:
        return err
    db = get_db()
    s = settings()
    if request.method == 'POST':
        data = payload(request.form)
        errors = validate(data)
        if not errors and db.permit_exists(data['permit_no'], exclude_id=id_):
            errors['permit_no'] = 'رقم التصريح مستخدم مسبقاً'
        if errors:
            data['id'] = id_
            return render_template('form.html', page='edit', c=data, errors=errors,
                                   settings=s, mode='edit'), 422
        changed = {k: v for k, v in data.items() if str(c.get(k)) != str(v)}
        db.update_contract(id_, data)
        log_audit('contracts.update', 'contract', id_,
                  {'permit_no': data['permit_no'], 'fields': list(changed.keys()),
                   'before': {k: c.get(k) for k in changed}})
        flash('تم تحديث التعاقد بنجاح', 'success')
        return redirect(url_for('view_contract', id_=id_))
    return render_template('form.html', page='edit', c=c, errors={}, settings=s, mode='edit')


@app.route('/contracts/<int:id_>')
@login_required
def view_contract(id_):
    c, err = require_contract(id_, 'view')
    if err:
        return err
    c['status'], c['status_label'] = status_of(c)
    c['is_mine'] = owns(c)
    doc = doclayout.build(dict(c, verify_domain=(settings().get('verify_domain') or '')),
                          verify_domain=settings().get('verify_domain'),
                          footer_url=(settings().get('official_verify_url') or OFFICIAL_VERIFY_URL))
    return render_template('view.html', page='dashboard', c=c, settings=settings(),
                           can_edit=can_edit(c), can_del=can_delete(c),
                           verify_url=verify_link(c),
                           doc_w=doc['w'], doc_h=doc['h'])


@app.route('/contracts/<int:id_>/delete', methods=['POST'])
@login_required
def delete_contract(id_):
    c, err = require_contract(id_, 'delete')
    if err:
        return err
    get_db().delete_contract(id_)
    log_audit('contracts.delete', 'contract', id_,
              {'permit_no': c['permit_no'], 'worker_name': c['worker_name']})
    flash(f'تم حذف التعاقد {c["permit_no"]}', 'success')
    return redirect(url_for('dashboard'))


@app.route('/contracts/<int:id_>/duplicate', methods=['POST'])
@permission_required('contracts.create')
def duplicate_contract(id_):
    c, err = require_contract(id_, 'view')
    if err:
        return err
    u = current_user()
    db = get_db()
    data = {k: c[k] for k in FIELDS}
    data['permit_no'] = gen_permit_no()
    data['created_by'] = u['id']
    data['created_by_name'] = display_name(u)
    data['created_by_email'] = u['email']
    data['verify_token'] = new_verify_token()
    row = db.create_contract(data)
    log_audit('contracts.duplicate', 'contract', row['id'],
              {'from': c['permit_no'], 'permit_no': data['permit_no']})
    flash('تم إنشاء نسخة جديدة من التعاقد', 'success')
    return redirect(url_for('edit_contract', id_=row['id']))


@app.route('/contracts')
@login_required
def contracts_index():
    """اختصار قائمة التعاقدات (نفس لوحة التحكم) — يحافظ على الروابط القديمة."""
    return redirect(url_for('dashboard', **request.args))


@app.route('/contracts/<int:id_>/print')
@login_required
def print_contract(id_):
    c, err = require_contract(id_, 'view')
    if err:
        return err
    if not can('contracts.print'):
        return render_template('error.html', page='', error='ليست لديك صلاحية طباعة الوثائق',
                               title='صلاحية غير كافية'), 403
    auto = request.args.get('auto', '1') != '0'
    return render_doc(c, 'print', auto)


@app.route('/contracts/<int:id_>/embed')
@login_required
def embed_contract(id_):
    c, err = require_contract(id_, 'view')
    if err:
        return err
    return render_doc(c, 'embed', False)


@app.route('/contracts/<int:id_>/pdf')
@login_required
def pdf_contract(id_):
    """توليد PDF مطابق للنموذج — fpdf2 + HarfBuzz (بدون أي مكتبات نظام)."""
    c, err = require_contract(id_, 'view')
    if err:
        return err
    if not can('contracts.export'):
        abort(403)
    ctx = doc_context(c)
    try:
        raw = build_pdf(ctx, qr_bytes(verify_link(c)), verify_domain=ctx['verify_domain'],
                        footer_url=ctx['footer_url'])
    except Exception:
        return redirect(url_for('print_contract', id_=id_, auto=0))
    log_audit('contracts.pdf', 'contract', id_, {'permit_no': c['permit_no']})
    buf = io.BytesIO(raw)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name=f'{c["permit_no"]}.pdf')


@app.route('/contracts/preview', methods=['POST'])
@login_required
def preview():
    raw = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    data = {k: (raw.get(k) or '').strip() for k in FIELDS}
    data.setdefault('id', 0)
    return render_doc(data, 'embed', False)


# ---------------------------------------------------------------- settings
@app.route('/settings', methods=['GET', 'POST'])
@permission_required('settings.manage')
def settings_page():
    db = get_db()
    if request.method == 'POST':
        changes = {}
        for k in ('org_name', 'verify_domain', 'verify_path', 'verify_title',
                  'official_verify_url', 'verify_partners', 'default_provider_name',
                  'default_provider_no', 'default_site'):
            v = (request.form.get(k) or '').strip()
            if k == 'verify_domain' or v:
                # نطاق التحقق يُحفظ فارغاً أيضاً = يتبع النطاق الذي تُفتح به المنصة
                db.save_setting(k, v)
                changes[k] = v
        log_audit('settings.update', 'settings', '', changes)
        flash('تم حفظ الإعدادات', 'success')
        return redirect(url_for('settings_page'))
    s = settings()
    return render_template('settings.html', page='settings', settings=s,
                           backend=db.backend, verify_base=verify_base(s))


# ---------------------------------------------------------------- admin
@app.route('/admin')
@login_required
def admin_page():
    if not can_any('users.view', 'permissions.view', 'audit.view'):
        return render_template('error.html', page='',
                               error='ليست لديك صلاحية الوصول إلى لوحة الإدارة',
                               title='صلاحية غير كافية'), 403
    tab = request.args.get('tab') or ('users' if can('users.view') or can('users.list') else 'audit')
    users, perms_map, counts = [], {}, {}
    try:
        if can('users.view'):
            users = store.list_users()
            perms_map = store.all_permissions_map()
            counts = get_db().counts_by_user()
    except Exception as e:
        flash(f'تعذّر تحميل المستخدمين: {e}', 'error')
    for u in users:
        u.pop('password_hash', None)
        u['permissions'] = perms_map.get(int(u['id']), [])
        u['is_owner'] = u.get('role') == 'owner'
        u['is_expired'] = account_expired(u)
        u['contract_count'] = counts.get(int(u['id']), 0)
        u['created_by_name'] = ''
    by_id = {int(u['id']): u for u in users}
    for u in users:
        cb = u.get('created_by')
        u['created_by_name'] = by_id[int(cb)]['full_name'] if cb and int(cb) in by_id else '—'

    audit, audit_total, audit_page, audit_pages = [], 0, 1, 1
    aq = (request.args.get('aq') or '').strip()
    aact = (request.args.get('action') or '').strip()
    aper = 40
    if can('audit.view') and tab == 'audit':
        try:
            audit_page = max(1, int(request.args.get('ap') or 1))
        except ValueError:
            audit_page = 1
        try:
            audit_total = store.count_audit_filtered(q=aq or None, action=aact or None)
        except Exception:
            audit_total = 0
        audit_pages = max(1, (audit_total + aper - 1) // aper)
        audit_page = min(audit_page, audit_pages)
        try:
            audit = store.list_audit(limit=aper, offset=(audit_page - 1) * aper,
                                     q=aq or None, action=aact or None)
        except Exception as e:
            flash(f'تعذّر تحميل سجل النشاط: {e}', 'error')

    stats = {
        'total': len(users),
        'active': sum(1 for u in users if u.get('is_active') and not u['is_expired']),
        'inactive': sum(1 for u in users if not u.get('is_active')),
        'expired': sum(1 for u in users if u['is_expired']),
        'suspended_contracts': 0,
    }
    audit_count = 0
    try:
        audit_count = store.count_audit()
    except Exception:
        pass
    return render_template('admin.html', page='admin', users=users, audit=audit,
                           stats=stats, tab=tab, audit_count=audit_count,
                           audit_total=audit_total, audit_page=audit_page, audit_pages=audit_pages,
                           aq=aq, aact=aact, role_presets=ROLE_PRESETS, roles=ROLE_LABELS,
                           max_perms=len(PERMISSION_KEYS),
                           perm_catalog=PERMISSION_CATALOG, catalog_by_category=catalog_by_category())


@app.route('/api/admin/users', methods=['GET', 'POST'])
@login_required
def api_users():
    if request.method == 'GET':
        if not can('users.view'):
            return jsonify(error='ليست لديك صلاحية عرض المستخدمين', code='FORBIDDEN'), 403
        users = store.list_users()
        pm = store.all_permissions_map()
        counts = get_db().counts_by_user()
        out = []
        for u in users:
            u = dict(u)
            u.pop('password_hash', None)
            u['permissions'] = pm.get(int(u['id']), [])
            u['contract_count'] = counts.get(int(u['id']), 0)
            out.append(u)
        return jsonify(out)

    # --- إنشاء مستخدم
    if not can('users.create'):
        return jsonify(error='ليست لديك صلاحية إنشاء مستخدمين جدد', code='FORBIDDEN',
                       required='users.create'), 403
    body = request.get_json(silent=True) or {}
    email = auth.normalize_email(body.get('email'))
    password = body.get('password') or ''
    full_name = (body.get('full_name') or '').strip()
    role = body.get('role') if body.get('role') in ('admin', 'user') else 'user'
    field_errors = {}
    if not auth.is_valid_email(email):
        field_errors['email'] = 'صيغة البريد الإلكتروني غير صحيحة'
    if not auth.is_valid_password(password):
        field_errors['password'] = 'كلمة المرور يجب ألا تقل عن 6 محرفاً'
    if not full_name:
        field_errors['full_name'] = 'الاسم الكامل مطلوب'
    limit, lerr = _parse_limit(body.get('contract_limit'))
    field_errors.update(lerr)
    expires, eerr = _parse_expiry(body)
    field_errors.update(eerr)
    if field_errors:
        return jsonify(error='تحقق من المدخلات', fieldErrors=field_errors), 400
    if store.get_user_by_email(email):
        return jsonify(error='البريد الإلكتروني مستخدم مسبقاً',
                       fieldErrors={'email': 'البريد الإلكتروني مستخدم مسبقاً'}), 409
    granted = [p for p in (body.get('permissions') or []) if p in PERMISSION_MAP]
    bad = auth.antiescalation_violations(current_user(), granted)
    if bad:
        labels = '، '.join(PERMISSION_MAP[p]['label'] for p in bad)
        return jsonify(error='لا يمكنك منح صلاحيات لا تملكها بنفسك: ' + labels,
                       code='FORBIDDEN'), 403
    try:
        user = store.create_user({
            'email': email, 'password_hash': auth.hash_password(password),
            'full_name': full_name, 'role': role,
            'is_active': bool(body.get('is_active', True)),
            'created_by': current_user()['id'],
            'contract_limit': limit, 'expires_at': expires,
        })
        store.set_permissions(user['id'], granted)
    except Exception as e:
        return jsonify(error='فشل إنشاء المستخدم: ' + str(e)), 500
    log_audit('users.create', 'user', user['id'],
              {'email': email, 'role': role, 'permissions': granted,
               'contract_limit': limit, 'expires_at': expires})
    return jsonify(ok=True, id=user['id'], message='تم إنشاء المستخدم بنجاح'), 201


@app.route('/api/admin/users/<int:uid>', methods=['PATCH', 'DELETE'])
@login_required
def api_user(uid):
    target = store.get_user(uid)
    if not target:
        return jsonify(error='المستخدم غير موجود', code='NOT_FOUND'), 404
    if is_owner(target) and request.method == 'DELETE':
        return jsonify(error='لا يمكن حذف حساب المالك', code='FORBIDDEN'), 403
    if is_owner(target):
        return jsonify(error='لا يمكن تعديل حساب المالك من هذه اللوحة. '
                             'يمكن للمالك تغيير بياناته من صفحة «حسابي».',
                       code='FORBIDDEN'), 403

    if request.method == 'DELETE':
        if not can('users.delete'):
            return jsonify(error='ليست لديك صلاحية حذف المستخدمين', code='FORBIDDEN',
                           required='users.delete'), 403
        if is_self(current_user(), target):
            return jsonify(error='لا يمكنك حذف حسابك الخاص'), 400
        try:
            store.delete_user(uid)
        except Exception as e:
            return jsonify(error='فشل حذف المستخدم: ' + str(e)), 500
        log_audit('users.delete', 'user', uid, {'email': target['email'],
                                                'full_name': target['full_name']})
        return jsonify(ok=True, message='تم حذف المستخدم نهائياً')

    body = request.get_json(silent=True) or {}
    changes = {}
    wants_perms = 'permissions' in body
    if wants_perms and not can('permissions.manage'):
        return jsonify(error='ليست لديك صلاحية إدارة الصلاحيات', code='FORBIDDEN',
                       required='permissions.manage'), 403
    if ('full_name' in body or 'email' in body or 'role' in body
            or 'contract_limit' in body or 'expires_at' in body) and not can('users.edit'):
        return jsonify(error='ليست لديك صلاحية تعديل بيانات المستخدمين', code='FORBIDDEN',
                       required='users.edit'), 403

    field_errors = {}
    if 'full_name' in body:
        name = (body.get('full_name') or '').strip()
        if not name:
            field_errors['full_name'] = 'الاسم الكامل مطلوب'
        else:
            changes['full_name'] = name
    if 'email' in body:
        email = auth.normalize_email(body.get('email'))
        if not auth.is_valid_email(email):
            field_errors['email'] = 'صيغة البريد الإلكتروني غير صحيحة'
        else:
            dup = store.get_user_by_email(email)
            if dup and int(dup['id']) != uid:
                field_errors['email'] = 'البريد الإلكتروني مستخدم مسبقاً'
            else:
                changes['email'] = email
    if 'role' in body and body.get('role') in ('admin', 'user'):
        changes['role'] = body['role']
    if 'contract_limit' in body:
        limit, lerr = _parse_limit(body.get('contract_limit'))
        field_errors.update(lerr)
        if not lerr:
            changes['contract_limit'] = limit
    if 'expires_at' in body:
        expires, eerr = _parse_expiry(body)
        field_errors.update(eerr)
        if not eerr:
            changes['expires_at'] = expires
    if field_errors:
        return jsonify(error='تحقق من المدخلات', fieldErrors=field_errors), 400

    granted = None
    if wants_perms:
        granted = [p for p in (body.get('permissions') or []) if p in PERMISSION_MAP]
        bad = auth.antiescalation_violations(current_user(), granted)
        if bad:
            labels = '، '.join(PERMISSION_MAP[p]['label'] for p in bad)
            return jsonify(error='لا يمكنك منح صلاحيات لا تملكها بنفسك: ' + labels,
                           code='FORBIDDEN'), 403

    try:
        if changes:
            store.update_user(uid, changes)
        if granted is not None:
            before = set(store.get_permissions(uid))
            store.set_permissions(uid, granted)
            changes['permissions_added'] = sorted(set(granted) - before)
            changes['permissions_removed'] = sorted(before - set(granted))
    except Exception as e:
        return jsonify(error='فشل تحديث المستخدم: ' + str(e)), 500
    log_audit('users.update', 'user', uid, dict(changes, email=changes.get('email', target['email'])))
    return jsonify(ok=True, message='تم تحديث بيانات المستخدم')


@app.route('/api/admin/users/<int:uid>/reset-password', methods=['POST'])
@login_required
def api_reset_password(uid):
    if not can('users.reset_password'):
        return jsonify(error='ليست لديك صلاحية إعادة تعيين كلمات المرور',
                       code='FORBIDDEN', required='users.reset_password'), 403
    target = store.get_user(uid)
    if not target:
        return jsonify(error='المستخدم غير موجود', code='NOT_FOUND'), 404
    if is_owner(target) and not is_self(current_user(), target):
        return jsonify(error='لا يمكن إعادة تعيين كلمة مرور المالك', code='FORBIDDEN'), 403
    body = request.get_json(silent=True) or {}
    pw = (body.get('password') or '').strip()
    if not auth.is_valid_password(pw):
        return jsonify(error='كلمة المرور يجب ألا تقل عن 6 محرفاً',
                       fieldErrors={'password': 'كلمة المرور يجب ألا تقل عن 6 محرفاً'}), 400
    try:
        store.update_user(uid, {'password_hash': auth.hash_password(pw)})
        store.delete_sessions_for_user(uid)
    except Exception as e:
        return jsonify(error='فشل تعيين كلمة المرور: ' + str(e)), 500
    log_audit('users.reset_password', 'user', uid, {'email': target['email']})
    return jsonify(ok=True, message='تم تعيين كلمة مرور جديدة وإنهاء جلسات المستخدم')


@app.route('/api/admin/users/<int:uid>/toggle-active', methods=['POST'])
@login_required
def api_toggle_active(uid):
    if not can('users.activate'):
        return jsonify(error='ليست لديك صلاحية تفعيل أو تعطيل الحسابات',
                       code='FORBIDDEN', required='users.activate'), 403
    target = store.get_user(uid)
    if not target:
        return jsonify(error='المستخدم غير موجود', code='NOT_FOUND'), 404
    if is_owner(target):
        return jsonify(error='لا يمكن تعطيل حساب المالك', code='FORBIDDEN'), 403
    if is_self(current_user(), target):
        return jsonify(error='لا يمكنك تعطيل حسابك الخاص'), 400
    new_state = not bool(target.get('is_active'))
    try:
        store.update_user(uid, {'is_active': new_state})
        if not new_state:
            store.delete_sessions_for_user(uid)
    except Exception as e:
        return jsonify(error='فشل تغيير حالة الحساب: ' + str(e)), 500
    log_audit('users.activate' if new_state else 'users.deactivate', 'user', uid,
              {'email': target['email'], 'is_active': new_state})
    return jsonify(ok=True, is_active=new_state,
                   message='تم تفعيل الحساب' if new_state else 'تم تعطيل الحساب وإنهاء جلساته')


@app.route('/api/admin/users/<int:uid>/contracts/<action>', methods=['POST'])
@login_required
def api_user_contracts(uid, action):
    """إيقاف (إلغاء) أو حذف جميع تعاقدات المستخدم."""
    if action not in ('revoke', 'delete'):
        return jsonify(error='إجراء غير معروف'), 400
    need = 'contracts.delete_all' if action == 'delete' else 'contracts.edit_all'
    if not can(need):
        return jsonify(error='ليست لديك الصلاحية المطلوبة لهذا الإجراء',
                       code='FORBIDDEN', required=need), 403
    target = store.get_user(uid)
    if not target:
        return jsonify(error='المستخدم غير موجود', code='NOT_FOUND'), 404
    db = get_db()
    try:
        n = db.count_by_user(uid)
        if action == 'delete':
            db.bulk_delete_user_contracts(uid)
        else:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            db.bulk_update_user_contracts(uid, {'end_date': yesterday})
    except Exception as e:
        return jsonify(error='فشل تنفيذ الإجراء: ' + str(e)), 500
    log_audit(f'contracts.bulk_{action}', 'user', uid,
              {'email': target['email'], 'affected': n})
    msg = (f'تم حذف {n} تعاقداً' if action == 'delete' else f'تم إلغاء {n} تعاقداً (انتهاء فوري)')
    return jsonify(ok=True, affected=n, message=msg)


@app.route('/api/admin/audit')
@login_required
def api_audit():
    if not can('audit.view'):
        return jsonify(error='ليست لديك صلاحية عرض سجل النشاط', code='FORBIDDEN',
                       required='audit.view'), 403
    try:
        limit = min(int(request.args.get('limit') or 100), 500)
    except ValueError:
        limit = 100
    rows = store.list_audit(limit=limit, q=(request.args.get('q') or '').strip() or None,
                            action=(request.args.get('action') or '').strip() or None)
    return jsonify(rows)


def _parse_limit(raw):
    if raw in (None, '', 'null'):
        return None, {}
    try:
        v = int(raw)
        if v < 0:
            raise ValueError
        return v, {}
    except (TypeError, ValueError):
        return None, {'contract_limit': 'الحد يجب أن يكون رقماً صحيحاً أو فارغاً (بلا حد)'}


def _parse_expiry(body):
    """expires_at مباشرة أو validity_months أو preset."""
    import calendar
    if 'expires_at' in body and body.get('expires_at') in (None, '', 'null'):
        return None, {}
    if body.get('expires_at'):
        try:
            d = datetime.fromisoformat(str(body['expires_at'])[:19])
            return d.replace(tzinfo=timezone.utc).isoformat(), {}
        except Exception:
            return None, {'expires_at': 'صيغة تاريخ الانتهاء غير صحيحة'}
    months = body.get('validity_months')
    if months in (None, '', 'null'):
        return None, {}
    try:
        m = int(months)
        now = datetime.now(timezone.utc)
        month = now.month - 1 + m
        year = now.year + month // 12
        month = month % 12 + 1
        day = min(now.day, calendar.monthrange(year, month)[1])
        return now.replace(year=year, month=month, day=day).isoformat(), {}
    except Exception:
        return None, {'expires_at': 'مدة الصلاحية غير صحيحة'}


@app.route('/api/me')
@login_required
def api_me():
    u = current_user()
    return jsonify(id=u['id'], email=u['email'], full_name=u['full_name'],
                   role=u['role'], is_active=u['is_active'],
                   is_owner=is_owner(u), permissions=sorted(permissions()),
                   contract_limit=u.get('contract_limit'),
                   expires_at=u.get('expires_at'))


# ---------------------------------------------------------------- public
MIN_TOKEN_LEN = 20


def _lookup_verify(key):
    """رمز التحقق العشوائي فقط للزوار.

    البحث برقم التصريح مسموح للمستخدمين المسجّلين فقط، لمنع تخمين/تعداد
    أرقام التصاريح من خارج المنصة.
    """
    if not key:
        return None
    key = key.strip()[:128]
    db = get_db()
    if len(key) >= MIN_TOKEN_LEN:
        c = db.get_by_token(key)
        if c:
            return c
    if auth.current_user():
        return db.get_by_permit(key)
    return None


def _render_verify(key):
    s = settings()
    lang = request.args.get('lang') or s.get('verify_lang') or 'ar'
    lang = 'en' if str(lang).lower().startswith('en') else 'ar'
    c = _lookup_verify(key)
    status = status_of(c) if c else ('unknown', 'غير موجود')
    partners = [u.strip() for u in (s.get('verify_partners') or '').split(',') if u.strip()]
    default_partners = [url_for('static', filename='img/takaml.png'),
                        url_for('static', filename='img/mlsd-logo.png')]
    resp = render_template('verify.html', c=c, status=status, settings=s, page='verify',
                           verify_key=key, lang=lang, partners=partners,
                           default_partners=default_partners,
                           title=s.get('verify_title') or 'تصريح أُجْير لحُلول الموارد البشرية',
                           hijri_year=hijri_year(),
                           hijri_year_ar=hijri_year().__str__().translate(
                               str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')))
    if not c:
        # تصريح غير موجود أو رمز غير صحيح → الموقع الرسمي، دون أي تفاصيل
        return official_redirect()
    return resp, 200


@app.route('/verify/')
@app.route('/verify')
@app.route('/agiar/index.php')
@app.route('/agiar/')
@app.route('/agiar')
def verify_gateway():
    """صفحة التحقق التي يفتحها رمز QR — /verify/?id=<token> (ويبقى /agiar/index.php اسماً بديلاً)"""
    key = (request.args.get('id') or request.args.get('t')
           or request.args.get('token') or request.args.get('code') or '').strip()
    if key.startswith('http'):
        key = key.split('id=')[-1]
    return _render_verify(key)


@app.route('/verify/<key>')
def verify(key):
    return _render_verify(key)


@app.route('/api/qr/<permit_no>.png')
@login_required
def qr_png(permit_no):
    """صورة QR — محمية، وتُبنى دائماً من رابط التحقق الرسمي للتصريح فقط."""
    c = get_db().get_by_permit(permit_no)
    if not c:
        abort(404)
    target = verify_link(c)
    buf = io.BytesIO(qr_bytes(target))
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@app.route('/api/health')
@login_required
def health():
    """حالة النظام — للإدارة فقط (لا تُكشف أي معلومات عامة)."""
    db = get_db()
    try:
        n = db.count()
        info = dict(status='ok', backend=db.backend, contracts=n,
                    time=datetime.now(timezone.utc).isoformat())
        try:
            info['users'] = store.count_users()
            info['auth'] = 'on'
        except Exception:
            info['auth'] = 'unavailable'
        return jsonify(info)
    except Exception as e:
        return jsonify(status='error', backend=db.backend, detail=str(e)), 500


@app.route('/robots.txt')
def robots_txt():
    return ('User-agent: *\nDisallow: /\n', 200,
            {'Content-Type': 'text/plain; charset=utf-8'})


@app.route('/favicon.ico')
def favicon():
    """أيقونة التبويب — شعار أجير الرسمي (نفس أيقونة ajeer.qiwa.sa)."""
    path = os.path.join(BASE_DIR, 'static', 'img', 'ajeer-mark.png')
    if os.path.exists(path):
        return send_file(path, mimetype='image/png', max_age=86400)
    return ('', 204)


@app.route('/site.webmanifest')
def webmanifest():
    """بيانات التطبيق (الاسم والأيقونة) لعنوان التبويب على الجوال."""
    return jsonify(
        name='أجير', short_name='أجير', start_url='/',
        display='standalone', background_color='#ffffff', theme_color='#05184D',
        dir='rtl', lang='ar',
        icons=[{'src': '/static/img/ajeer-mark.png', 'sizes': '360x360', 'type': 'image/png',
                'purpose': 'any maskable'}],
    )


@app.errorhandler(404)
def not_found(e):
    # لا صفحة خطأ للزوار: تحويل فوري إلى الموقع الرسمي
    if request.method in ('GET', 'HEAD') and not request.path.startswith(('/api/', '/static/')):
        return official_redirect()
    return render_template('404.html', page=''), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', page='', error='ليست لديك صلاحية للوصول إلى هذه الصفحة',
                           title='صلاحية غير كافية'), 403


@app.errorhandler(429)
def too_many(e):
    return render_template('error.html', page='',
                           error='محاولات كثيرة. يرجى المحاولة بعد قليل.',
                           title='محاولات كثيرة'), 429


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', page='', error='حدث خطأ غير متوقع'), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=bool(os.environ.get('DEBUG')))
