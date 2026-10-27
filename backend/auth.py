# -*- coding: utf-8 -*-
"""
المصادقة والصلاحيات — مستوحى من نموذج لوحة «بلدي».
  • كلمات المرور: scrypt (s2:<salt>:<hash>) مع مقارنة زمنية ثابتة
  • الجلسات: توكن عشوائي 32 بايت، يُخزَّن هاش SHA-256 فقط، صلاحية 30 يوماً
  • الصلاحيات: كتالوج دقيق + المالك يملك كل شيء ضمنياً
  • سجل النشاط: تسجيل أفضل-جهد لا يُفشل العملية
"""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (abort, g, jsonify, redirect, request, session as flask_session,
                   url_for)

import authstore as store
from permissions import PERMISSION_KEYS, PERMISSION_MAP, ROLE_LABELS

COOKIE_NAME = 'aj_session'
SESSION_DAYS = 30
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 16384, 8, 1, 64

# المسارات الوحيدة المتاحة بدون تسجيل دخول:
#   • صفحة الدخول/الخروج
#   • صفحة التحقق التي يفتحها رمز QR  (/verify/?id=…)
#   • روابط التحقق القديمة /verify/<token>
#   • الملفات الثابتة (CSS/خطوط/شعارات) اللازمة لعرض صفحة التحقق
#   • robots.txt و favicon
PUBLIC_ENDPOINTS = {
    'static', 'login', 'logout',
    'verify_gateway', 'verify',
    'robots_txt', 'favicon', 'webmanifest',
}

# بادئات لا تُسجَّل محاولاتها (ملفات ثابتة / متصفح)
_NOISE_PREFIXES = ('/static/', '/robots.txt', '/favicon.ico', '/site.webmanifest', '/.well-known/')


# ------------------------------------------------------------------ hashing
def hash_password(password):
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=SCRYPT_N,
                        r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN)
    return f's2:{salt.hex()}:{dk.hex()}'


def verify_password(password, stored):
    try:
        algo, salt_hex, hash_hex = (stored or '').split(':')
        if algo != 's2':
            return False
        dk = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt_hex),
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def is_valid_password(pw):
    return isinstance(pw, str) and len(pw) >= 6 and not pw.isspace()


EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')


def is_valid_email(email):
    return bool(email) and bool(EMAIL_RE.match(email))


def normalize_email(email):
    return (email or '').strip().lower()


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


# ------------------------------------------------------------------ sessions
def _cookie_secure():
    base = (os.environ.get('PUBLIC_BASE_URL') or '')
    return base.startswith('https') or request.is_secure


def start_session(user):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS))
    store.create_session(user['id'], token_hash(token), expires.isoformat(),
                         request.headers.get('User-Agent'), _client_ip())
    store.update_user(user['id'], {'last_login_at': datetime.now(timezone.utc).isoformat()})
    flask_session.permanent = False
    return token, expires


def set_session_cookie(resp, token):
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_DAYS * 86400,
                    httponly=True, samesite='Lax', secure=_cookie_secure(), path='/')


def clear_session_cookie(resp):
    resp.delete_cookie(COOKIE_NAME, path='/')


def _client_ip():
    fwd = request.headers.get('X-Forwarded-For') or ''
    return (fwd.split(',')[0].strip() if fwd else (request.remote_addr or ''))[:64]


def _extract_token():
    auth = request.headers.get('Authorization') or ''
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    return (request.cookies.get(COOKIE_NAME)
            or request.args.get('token')
            or (request.get_json(silent=True) or {}).get('token')
            if request.method in ('POST', 'GET') else request.cookies.get(COOKIE_NAME))


# ------------------------------------------------------------------ user ctx
def load_current_user():
    """يُستدعى في before_request — يملأ g.user / g.perms باستعلام واحد."""
    g.user = None
    g.perms = set()
    g.session_token = None
    if request.path.startswith('/static/'):
        return
    token = (request.cookies.get(COOKIE_NAME) or _bearer()
             or (request.args.get('token') if request.path.startswith('/api/') else None))
    if not token:
        return
    th = token_hash(token)
    try:
        sess, user = store.get_session_with_user(th)
    except Exception:
        return
    if not sess:
        return
    try:
        exp = _parse_dt(sess.get('expires_at'))
        if exp and exp < datetime.now(timezone.utc):
            store.delete_session(th)
            return
    except Exception:
        return
    if not user or not user.get('is_active'):
        return
    if user.get('expires_at') and _parse_dt(user['expires_at']) < datetime.now(timezone.utc):
        return
    g.user = user
    g.session_token = th
    g.perms = (set(PERMISSION_KEYS) if user.get('role') == 'owner'
               else set(store.get_permissions(user['id'])))
    store.touch_session(th)


def _bearer():
    a = request.headers.get('Authorization') or ''
    return a[7:].strip() if a.lower().startswith('bearer ') else None


def _parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        s = str(v).replace('Z', '+00:00')
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_public_endpoint():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return True
    return request.path.startswith('/static/')


def gate():
    """بوابة مركزية: كل ما ليس عاماً يتطلب جلسة صحيحة — وإلا يُحجب فوراً."""
    if request.method == 'OPTIONS':
        return None
    if is_public_endpoint():
        return None
    if current_user():
        return None
    # مسار محمي أو غير معروف بدون جلسة → لا نكشف وجوده
    if request.path.startswith('/api/') or wants_json():
        return jsonify(error='يجب تسجيل الدخول للمتابعة', code='AUTH_REQUIRED'), 401
    target = request.full_path if request.query_string else request.path
    if not target.startswith('/') or target.startswith('//'):
        target = '/'
    return redirect(url_for('login', next=target))


_denied_cache = {}
DENIED_LOG_TTL = 600  # ثانية — نفس العنوان مرة واحدة كل 10 دقائق


def log_denied(reason='AUTH_REQUIRED'):
    """تسجيل محاولة وصول غير مصرّح بها (مع خنق لمنع إغراق السجل)."""
    import time as _t
    path = (request.path or '/')[:120]
    if path.startswith(_NOISE_PREFIXES):
        return
    ip = _client_ip()
    key = (ip, path, reason)
    now = _t.time()
    if len(_denied_cache) > 2000:
        for k, v in list(_denied_cache.items()):
            if now - v > DENIED_LOG_TTL:
                _denied_cache.pop(k, None)
    last = _denied_cache.get(key)
    if last and now - last < DENIED_LOG_TTL:
        return
    _denied_cache[key] = now
    try:
        store.add_audit(None, 'system', 'security.denied', 'route', path,
                        {'method': request.method, 'reason': reason,
                         'ip': ip,
                         'ua': (request.headers.get('User-Agent') or '')[:120]})
    except Exception:
        pass


def current_user():
    return getattr(g, 'user', None)


def permissions():
    return getattr(g, 'perms', set())


def can(perm):
    u = current_user()
    if not u:
        return False
    if u.get('role') == 'owner':
        return True
    return perm in permissions()


def can_any(*perms):
    return any(can(p) for p in perms)


# ------------------------------------------------------------------ guards
def wants_json():
    return (request.path.startswith('/api/') or
            'application/json' in (request.headers.get('Accept') or '') or
            request.is_json)


def deny(message='يجب تسجيل الدخول للمتابعة', code='AUTH_REQUIRED', status=401, required=None):
    if wants_json():
        payload = {'error': message, 'code': code}
        if required:
            payload['required'] = required
        return jsonify(payload), status
    if code == 'AUTH_REQUIRED':
        return redirect(url_for('login', next=request.full_path if request.query_string else request.path))
    return _forbidden_page(message), 403


def _forbidden_page(message):
    from flask import render_template
    return render_template('error.html', page='', error=message, title='صلاحية غير كافية'), 403


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return deny()
        return fn(*a, **kw)
    return wrapper


def permission_required(perm):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return deny()
            if not can(perm):
                label = PERMISSION_MAP.get(perm, {}).get('label', perm)
                return deny(f'ليست لديك صلاحية «{label}»', 'FORBIDDEN', 403, perm)
            return fn(*a, **kw)
        return wrapper
    return deco


def any_permission(*perms):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return deny()
            if not can_any(*perms):
                return deny('ليست لديك صلاحية للقيام بهذا الإجراء', 'FORBIDDEN', 403,
                            list(perms))
            return fn(*a, **kw)
        return wrapper
    return deco


# ------------------------------------------------------------------ audit
def log_audit(action, entity='', entity_id='', details=None):
    """أفضل-جهد: لا يُفشل العملية أبداً."""
    try:
        u = current_user()
        store.add_audit(u['id'] if u else None,
                        u['email'] if u else 'system',
                        action, entity, entity_id, details or {})
    except Exception:
        pass


# ------------------------------------------------------------------ business rules
def is_owner(user):
    return bool(user) and user.get('role') == 'owner'


def is_self(user, target):
    return bool(user and target and int(user['id']) == int(target['id']))


def can_manage_target(target):
    """المالك لا يُدار من أي أحد (ولا حتى من نفسه عبر هذه الواجهة)."""
    return not is_owner(target)


def antiescalation_violations(actor, granted):
    """غير المالك لا يمنح صلاحيات لا يملكها هو نفسه."""
    if is_owner(actor):
        return []
    held = set(permissions())
    return [p for p in granted if p not in held]


def certificate_quota(user, used):
    limit = user.get('contract_limit')
    if limit is None:
        return True, None
    if used >= int(limit):
        return False, f'بلغت الحد الأقصى المسموح ({limit}) من التعاقدات'
    return True, None


def account_expired(user):
    v = user.get('expires_at')
    if not v:
        return False
    d = _parse_dt(v)
    return bool(d and d < datetime.now(timezone.utc))


# ------------------------------------------------------------------ bootstrap
_bootstrapped = False


def ensure_bootstrap():
    """تهيئة حساب المالك الأول إذا كان الجدول فارغاً."""
    global _bootstrapped
    if _bootstrapped:
        return
    try:
        if store.count_users() == 0:
            email = normalize_email(os.environ.get('OWNER_EMAIL') or 'admin@ajeer.sa')
            pw = os.environ.get('OWNER_PASSWORD') or 'Ajeer@2026'
            name = os.environ.get('OWNER_NAME') or 'مالك المنصة'
            u = store.create_user({
                'email': email, 'password_hash': hash_password(pw),
                'full_name': name, 'role': 'owner', 'is_active': True,
            })
            store.add_audit(u['id'] if u else None, 'system', 'system.bootstrap',
                            'user', (u or {}).get('id', ''), {'email': email})
    except Exception:
        return
    _bootstrapped = True


def display_name(user):
    if not user:
        return ''
    return user.get('full_name') or (user.get('email') or '').split('@')[0]


def initials(user):
    n = display_name(user).strip()
    return n[0] if n else '؟'


def role_label(role):
    return ROLE_LABELS.get(role, role)
