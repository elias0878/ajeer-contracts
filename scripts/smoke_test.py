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

    # --- الصفحات ---
    for path, needle in [
        ('/', 'لوحة التحكم'),
        ('/contracts/new', 'إنشاء تعاقد جديد'),
        ('/settings', 'إعدادات المنصة'),
        ('/verify/TQ101515442', 'TQ101515442'),
        ('/contracts/1', 'تفاصيل التعاقد'),
        ('/contracts/1/embed', 'تعاقد اجير'),
        ('/contracts/1/print?auto=0', 'إقرارات'),
    ]:
        r = client.get(path)
        check(f'GET {path}', r.status_code == 200 and needle in r.get_data(as_text=True))

    # --- حالة النظام ---
    r = client.get('/api/health')
    js = r.get_json() or {}
    check('GET /api/health', r.status_code == 200 and js.get('status') == 'ok', str(js))

    # --- PDF ---
    r = client.get('/contracts/1/pdf')
    pdf = r.data
    check('PDF content-type', r.headers.get('Content-Type') == 'application/pdf')
    check('PDF signature', pdf[:5] == b'%PDF-', pdf[:20])
    check('PDF size > 50KB', len(pdf) > 50_000, str(len(pdf)))
    check('PDF page letter', b'/MediaBox [0 0 612 792]' in pdf or b'612' in pdf)

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
