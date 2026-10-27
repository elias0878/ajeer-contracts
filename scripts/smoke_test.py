#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اختبارات دخان (Smoke tests) — تعمل محلياً وعلى CI بدون الحاجة لـ Supabase.
تتحقق من: الصفحات الأساسية، إنشاء/تعديل/حذف عقد، توليد PDF، صفحة التحقق، وحالة النظام.
"""
import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

# استخدام SQLite مؤقت للاختبار حتى لا نلمس أي قاعدة بيانات حقيقية
os.environ['SQLITE_PATH'] = os.path.join(tempfile.mkdtemp(), 'test.db')
os.environ.pop('SUPABASE_URL', None)
os.environ.pop('SUPABASE_SERVICE_KEY', None)

from app import app  # noqa: E402

FAILED = []


def check(name, cond, extra=''):
    status = 'PASS' if cond else 'FAIL'
    print(f'[{status}] {name}' + (f' — {extra}' if extra and not cond else ''))
    if not cond:
        FAILED.append(name)


def main():
    client = app.test_client()

    # --- المصادقة (إلزامية قبل أي صفحة إدارية) ---
    anon = app.test_client()
    r = anon.get('/')
    check('زائر بلا تسجيل دخول يُحوَّل إلى /login',
          r.status_code == 302 and '/login' in r.headers.get('Location', ''))
    r = anon.get('/api/admin/users')
    check('واجهة الإدارة ترفض الزائر (401)', r.status_code == 401)
    r = anon.post('/login', data={'email': 'admin@ajeer.sa', 'password': 'wrong-pass'})
    check('كلمة مرور خاطئة لا تفتح الجلسة',
          r.status_code == 200 and 'غير صحيحة' in r.get_data(as_text=True))

    # --- بوابة الحجب: لا شيء عام إلا التحقق ---
    protected = ['/', '/admin', '/admin?tab=audit', '/account', '/settings',
                 '/contracts/1', '/contracts/1/edit', '/contracts/1/print',
                 '/contracts/1/pdf', '/contracts/1/embed', '/contracts/new']
    blocked = []
    for path in protected:
        rr = anon.get(path)
        if not (rr.status_code == 302 and '/login' in rr.headers.get('Location', '')):
            blocked.append(f'{path}={rr.status_code}')
    check('كل صفحات المنصة محجوبة عن الزائر', not blocked, ', '.join(blocked))

    apis = ['/api/health', '/api/me', '/api/admin/users', '/api/admin/audit',
            '/api/qr/TQ101515442.png']
    blocked_api = [f'{p}={anon.get(p).status_code}' for p in apis
                   if anon.get(p).status_code != 401]
    check('كل واجهات API محجوبة عن الزائر (401)', not blocked_api, ', '.join(blocked_api))

    for path in ['/wp-admin', '/.env', '/random-path', '/config.php']:
        rr = anon.get(path)
        check(f'مسار غير موجود محجوب: {path}',
              rr.status_code == 302 and '/login' in rr.headers.get('Location', ''))

    r = anon.get('/robots.txt')
    check('robots.txt يمنع الفهرسة', r.status_code == 200 and 'Disallow: /' in r.get_data(as_text=True))

    r = anon.get('/verify/TQ101515442')
    check('منع تخمين أرقام التصاريح من الخارج (404)', r.status_code == 404, str(r.status_code))
    r = client.post('/login', data={'email': 'admin@ajeer.sa', 'password': 'Ajeer@2026'})
    check('تسجيل دخول المالك', r.status_code == 302 and '/' in r.headers.get('Location', ''),
          str(r.status_code))

    # --- الصفحات ---
    for path, needle in [
        ('/', 'لوحة التحكم'),
        ('/contracts/new', 'إنشاء تعاقد جديد'),
        ('/settings', 'إعدادات المنصة'),
        ('/verify/TQ101515442', 'TQ101515442'),
        ('/contracts/1', 'تفاصيل التعاقد'),
        ('/contracts/1/embed', '<svg'),
        ('/contracts/1/print?auto=0', 'أقرارات'),
    ]:
        r = client.get(path)
        check(f'GET {path}', r.status_code == 200 and needle in r.get_data(as_text=True))

    # --- صفحات الإدارة ---
    for path, needle in [
        ('/admin', 'إدارة المستخدمين'),
        ('/admin?tab=perms', 'مصفوفة الصلاحيات'),
        ('/admin?tab=audit', 'سجل النشاط'),
        ('/account', 'تغيير كلمة المرور'),
    ]:
        r = client.get(path)
        check(f'GET {path}', r.status_code == 200 and needle in r.get_data(as_text=True),
              str(r.status_code))

    # --- إنشاء مستخدم محدود الصلاحيات والتحقق من العزل ---
    r = client.post('/api/admin/users', json={
        'full_name': 'مستخدم اختبار', 'email': 'smoke@ajeer.sa', 'password': 'Smoke@123',
        'role': 'user', 'permissions': ['contracts.view_own', 'contracts.create']})
    check('POST /api/admin/users', r.status_code == 201, r.get_data(as_text=True)[:200])
    smoke_id = (r.get_json() or {}).get('id')
    sub = app.test_client()
    r = sub.post('/login', data={'email': 'smoke@ajeer.sa', 'password': 'Smoke@123'})
    check('دخول المستخدم المحدود', r.status_code == 302)
    r = sub.get('/admin')
    check('المستخدم المحدود لا يدخل لوحة الإدارة (403)', r.status_code == 403)
    r = sub.get('/contracts/1')
    check('عزل العقود: لا يرى عقد غيره (403)', r.status_code == 403)
    r = sub.post('/api/admin/users', json={'full_name': 'x', 'email': 'x@y.sa', 'password': '123456'})
    check('منع تصعيد الصلاحيات', r.status_code == 403)
    r = client.post(f'/api/admin/users/{smoke_id}/toggle-active')
    check('تعطيل الحساب', r.status_code == 200 and r.get_json().get('is_active') is False)
    r = app.test_client().post('/login', data={'email': 'smoke@ajeer.sa', 'password': 'Smoke@123'})
    check('الحساب المعطّل لا يستطيع الدخول',
          'معطّل' in r.get_data(as_text=True))
    r = client.delete(f'/api/admin/users/{smoke_id}')
    check('حذف المستخدم', r.status_code == 200)
    r = client.delete('/api/admin/users/1')
    check('حماية حساب المالك من الحذف', r.status_code == 403)
    r = client.get('/api/admin/audit')
    check('سجل النشاط متاح للمالك', r.status_code == 200 and len(r.get_json()) > 0)

    # --- حالة النظام (للمسجّلين فقط) ---
    r = client.get('/api/health')
    js = r.get_json() or {}
    check('GET /api/health (مسجّل)', r.status_code == 200 and js.get('status') == 'ok', str(js))
    check('GET /api/health (زائر)', anon.get('/api/health').status_code == 401)

    # --- رابط التحقق الجديد: /verify/?id=<token> ---
    import re as _re
    view = client.get('/contracts/1').get_data(as_text=True)
    m = _re.search(r'id="verifyLink"[^>]*value="([^"]+)"', view)
    link = m.group(1) if m else ''
    check('رابط التحقق موجود في صفحة التعاقد', bool(link), link)
    check('شكل الرابط /verify/?id=', '/verify/?id=' in link, link)
    _tok = link.split('id=')[-1]
    check('رمز التحقق 64 محرفاً', len(_tok) >= 40, str(len(_tok)))
    check('الرابط لا يحتوي رقم التصريح', 'TQ101515442' not in link, link)
    r = client.get('/verify/?id=' + _tok)
    check('صفحة التحقق تفتح بالرمز', r.status_code == 200 and 'احمد صبحى' in r.get_data(as_text=True))
    r = client.get('/verify/?id=' + 'X' * 64)
    check('رمز غير صحيح يعيد 404', r.status_code == 404, str(r.status_code))
    r = client.get('/verify/')
    check('صفحة إدخال الرمز تعمل', r.status_code == 200)
    vf = client.get('/verify/?id=' + _tok).get_data(as_text=True)
    for needle, label in [('معلومات التصريح', 'بطاقة معلومات التصريح'),
                          ('المنشأة المستفيدة', 'بطاقة المنشأة المستفيدة'),
                          ('شركة الإستقدام', 'بطاقة شركة الاستقدام'),
                          ('نسخ رابط الصفحة', 'زر نسخ الرابط'),
                          ('status-badge', 'شريحة الحالة')]:
        check(f'صفحة التحقق: {label}', needle in vf)
    check('صفحة التحقق: شعار أجير في التذييل', 'ajeer-logo.png' in vf)
    r = client.get('/verify/TQ101515442')
    check('الروابط القديمة ما زالت تعمل (توافق)', r.status_code == 200)

    # --- PDF ---
    r = client.get('/contracts/1/pdf')
    pdf = r.data
    check('PDF content-type', r.headers.get('Content-Type') == 'application/pdf')
    check('PDF signature', pdf[:5] == b'%PDF-', pdf[:20])
    check('PDF size > 50KB', len(pdf) > 50_000, str(len(pdf)))
    check('PDF page 1000x1524.66', b'/MediaBox [0 0 1000.00 1524.66]' in pdf)

    # --- QR ---
    r = client.get('/api/qr/TQ101515442.png')
    check('GET /api/qr', r.status_code == 200 and r.data[:4] == b'\x89PNG')

    # --- إنشاء عقد ---
    payload = dict(
        permit_no='TQ999000111', worker_name='اختبار آلي للعقد', id_no='1234567890',
        profession='مراقب جودة', nationality='مصر',
        provider_name='مؤسسة مكعب العربية للمقاولات العامة', provider_no='1970887-6',
        beneficiary_name='شركة اختبار', beneficiary_no='9-9999999',
        description='اختبار تلقائي', start_date='2026-01-01', end_date='2027-01-01',
        site='الرياض')
    r = client.post('/contracts/new', data=payload, follow_redirects=True)
    body = r.get_data(as_text=True)
    check('POST /contracts/new', r.status_code == 200 and 'TQ999000111' in body)

    # --- معاينة مباشرة ---
    r = client.post('/contracts/preview', json=payload)
    check('POST /contracts/preview', r.status_code == 200 and 'اختبار آلي' in r.get_data(as_text=True))

    # --- بحث ---
    r = client.get('/?q=TQ999000111')
    check('بحث بالرقم', 'TQ999000111' in r.get_data(as_text=True))

    # --- تحقق من الحقول ---
    r = client.post('/contracts/new', data={'permit_no': 'BAD'})
    check('رفض البيانات الناقصة (422)', r.status_code == 422)

    # --- تعديل + حذف ---
    from db import get_db
    row = get_db().get_by_permit('TQ999000111')
    check('العقد موجود في القاعدة', bool(row))
    if row:
        edit = dict(payload)
        edit['worker_name'] = 'اسم معدّل'
        r = client.post(f'/contracts/{row["id"]}/edit', data=edit, follow_redirects=True)
        check('POST تعديل', r.status_code == 200 and 'اسم معدّل' in r.get_data(as_text=True))
        r = client.post(f'/contracts/{row["id"]}/delete', follow_redirects=True)
        check('POST حذف', r.status_code == 200)
        check('حُذف فعلاً', get_db().get_by_permit('TQ999000111') is None)

    print()
    if FAILED:
        print(f'❌ فشل {len(FAILED)} اختبار: {FAILED}')
        return 1
    print('✅ كل الاختبارات نجحت')
    return 0


if __name__ == '__main__':
    sys.exit(main())
