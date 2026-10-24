# -*- coding: utf-8 -*-
"""
كتالوج الصلاحيات — المصدر الوحيد للحقيقة (خادم + واجهة).
المالك (role='owner') يملك كل الصلاحيات ضمنياً ولا تُعدَّل صلاحياته.
"""

PERMISSION_CATALOG = [
    # ---------------- العقود ----------------
    dict(key='contracts.view_all', category='العقود', label='عرض جميع العقود',
         description='رؤية سجل التعاقدات كاملاً الصادر من جميع المستخدمين'),
    dict(key='contracts.view_own', category='العقود', label='عرض العقود الخاصة به',
         description='رؤية التعاقدات التي أنشأها هذا المستخدم فقط'),
    dict(key='contracts.create', category='العقود', label='إنشاء تعاقد جديد',
         description='إضافة وإصدار تصاريح تعاقد جديدة'),
    dict(key='contracts.edit_all', category='العقود', label='تعديل جميع العقود',
         description='تعديل بيانات أي تعاقد بغض النظر عن منشئه'),
    dict(key='contracts.edit_own', category='العقود', label='تعديل العقود الخاصة به',
         description='تعديل التعاقدات التي أنشأها هذا المستخدم فقط'),
    dict(key='contracts.delete_all', category='العقود', label='حذف جميع العقود',
         description='حذف أي تعاقد نهائياً'),
    dict(key='contracts.delete_own', category='العقود', label='حذف العقود الخاصة به',
         description='حذف التعاقدات التي أنشأها هذا المستخدم فقط'),
    dict(key='contracts.links', category='العقود', label='نسخ الروابط ورموز QR',
         description='عرض ونسخ روابط التحقق المباشرة ورموز QR'),
    dict(key='contracts.print', category='العقود', label='معاينة وطباعة الوثائق',
         description='فتح مستند التصريح للطباعة أو المعاينة'),
    dict(key='contracts.export', category='العقود', label='تصدير PDF',
         description='تنزيل مستند التصريح بصيغة PDF'),

    # ---------------- المستخدمون ----------------
    dict(key='users.view', category='المستخدمون', label='عرض قائمة المستخدمين',
         description='الاطلاع على الحسابات المسجلة وبياناتها'),
    dict(key='users.create', category='المستخدمون', label='إنشاء مستخدمين جدد',
         description='إضافة حسابات جديدة بالبريد الإلكتروني وكلمة المرور'),
    dict(key='users.edit', category='المستخدمون', label='تعديل بيانات المستخدمين',
         description='تعديل الاسم والبريد الإلكتروني والدور والحدود'),
    dict(key='users.reset_password', category='المستخدمون', label='إعادة تعيين كلمات المرور',
         description='تعيين كلمة مرور جديدة لأي مستخدم'),
    dict(key='users.activate', category='المستخدمون', label='تفعيل أو تعطيل الحسابات',
         description='إيقاف حساب مؤقتاً أو إعادة تفعيله'),
    dict(key='users.delete', category='المستخدمون', label='حذف المستخدمين',
         description='حذف الحسابات نهائياً (لا يُحذف المالك أبداً)'),

    # ---------------- الصلاحيات ----------------
    dict(key='permissions.view', category='الصلاحيات', label='عرض صلاحيات المستخدمين',
         description='الاطلاع على الصلاحيات الممنوحة لكل مستخدم'),
    dict(key='permissions.manage', category='الصلاحيات', label='إدارة ومنح وتعديل الصلاحيات',
         description='إضافة صلاحيات أو إيقافها أو تعديلها لأي مستخدم في أي وقت'),

    # ---------------- المراقبة ----------------
    dict(key='audit.view', category='المراقبة', label='عرض سجل النشاط',
         description='متابعة كل عمليات الإنشاء والتعديل والحذف وإدارة الحسابات'),

    # ---------------- النظام ----------------
    dict(key='settings.manage', category='النظام', label='إدارة إعدادات المنصة',
         description='تعديل نطاق التحقق والبيانات الافتراضية للعقود'),
]

PERMISSION_KEYS = [p['key'] for p in PERMISSION_CATALOG]
PERMISSION_MAP = {p['key']: p for p in PERMISSION_CATALOG}
CATEGORIES = []
for _p in PERMISSION_CATALOG:
    if _p['category'] not in CATEGORIES:
        CATEGORIES.append(_p['category'])


def is_known(key):
    return key in PERMISSION_MAP


def catalog_by_category():
    out = {c: [] for c in CATEGORIES}
    for p in PERMISSION_CATALOG:
        out[p['category']].append(p)
    return out


ROLE_LABELS = {'owner': 'المالك', 'admin': 'مدير', 'user': 'مستخدم'}

# صلاحيات مقترحة لكل دور عند الإنشاء السريع
ROLE_PRESETS = {
    'admin': [
        'contracts.view_all', 'contracts.create', 'contracts.edit_all', 'contracts.delete_all',
        'contracts.links', 'contracts.print', 'contracts.export',
        'users.view', 'permissions.view', 'audit.view',
    ],
    'user': [
        'contracts.view_own', 'contracts.create', 'contracts.edit_own', 'contracts.delete_own',
        'contracts.links', 'contracts.print', 'contracts.export',
    ],
}
