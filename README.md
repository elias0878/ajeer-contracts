<div align="center">

# 📄 منصة إدارة وإنشاء العقود — تعاقد أجير

**نظام ويب عربي (RTL) لإدارة العقود وتصاريح العمل، يولّد مستند PDF مطابقاً للنموذج الرسمي حرفياً.**

[![Vercel](https://img.shields.io/badge/Vercel-Live-000?logo=vercel&logoColor=white)](https://ajeer-contracts.vercel.app)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase&logoColor=white)](https://supabase.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)

</div>

---

## ✨ المزايا

| الميزة | الوصف |
|---|---|
| 🗂️ **إدارة كاملة للعقود** | إنشاء، عرض، تعديل، تكرار، حذف، بحث، تصفية حسب الحالة |
| 🖊️ **معاينة حيّة** | المستند يتحدّث أثناء الكتابة في النموذج |
| 📄 **PDF مطابق للنموذج** | 612×792pt، نفس الحدود والخطوط وأحجام النص وموضع رمز QR |
| 🔳 **رمز QR للتحقق** | يفتح صفحة تحقق عامة تعرض حالة التصريح وصلاحيته |
| 📊 **لوحة تحكم** | إحصاءات: إجمالي / سارية / تنتهي خلال 30 يوماً / منتهية |
| ☁️ **قاعدة بيانات سحابية** | Supabase (PostgreSQL) عبر PostgREST، مع احتياطي SQLite محلي |
| ⚡ **Serverless** | يعمل على Vercel Python Runtime بدون أي مكتبات نظام |

---

## 🧱 المعمارية

```
العميل (RTL/HTML/CSS/JS)
        │
        ▼
   Flask App  ──►  pdfdoc.py (fpdf2 + HarfBuzz)  ──►  PDF 612×792pt
        │
        ▼
   db.py  ──►  Supabase REST (PostgREST)  /  SQLite (تطوير)
```

```
ajeer-contracts/
├── api/index.py            # نقطة دخول Vercel
├── vercel.json             # إعدادات النشر
├── requirements.txt
├── backend/
│   ├── app.py              # مسارات Flask
│   ├── db.py               # طبقة البيانات (Supabase / SQLite)
│   ├── pdfdoc.py           # مُولّد المستند (إحداثيات مقيسة من النموذج)
│   ├── templates/          # قوالب Jinja2 (RTL)
│   └── static/             # CSS + خطوط Almarai + الشعار
└── scripts/
```

---

## 🚀 التشغيل المحلي

```bash
# 1) المكتبات
pip install -r requirements.txt

# 2) (اختياري) متغيرات البيئة للاتصال بـ Supabase
export SUPABASE_URL="https://<ref>.supabase.co"
export SUPABASE_SERVICE_KEY="<service_role_key>"

# 3) التشغيل
cd backend && python app.py     # http://localhost:5000
```

بدون متغيرات البيئة يعمل التطبيق تلقائياً على **SQLite** محلي مع بيانات تجريبية.

---

## 🔌 واجهات API

| المسار | الوصف |
|---|---|
| `GET /` | لوحة التحكم |
| `GET /contracts/new` · `POST` | إنشاء تعاقد |
| `GET /contracts/<id>` | تفاصيل التعاقد |
| `GET /contracts/<id>/edit` · `POST` | تعديل |
| `POST /contracts/<id>/delete` | حذف |
| `POST /contracts/<id>/duplicate` | تكرار |
| `GET /contracts/<id>/pdf` | تحميل PDF |
| `GET /contracts/<id>/print` | صفحة طباعة |
| `POST /contracts/preview` | معاينة حيّة (HTML) |
| `GET /verify/<permit_no>` | صفحة التحقق العامة (QR) |
| `GET /api/qr/<permit_no>.png` | صورة QR |
| `GET /api/health` | حالة النظام والقاعدة |

---

## 📐 دقة المستند

تم استخراج إحداثيات النموذج الرسمي من ملف PDF مرجعي ثم ضبطها رقمياً:

| العنصر | القيمة |
|---|---|
| مقاس الصفحة | 612 × 792 pt (Letter) |
| الترويسة | (59.5, 27.8) → 506 × 79.6 pt |
| رمز QR | (69.5, 29.9) — 59.1 × 49.5 pt |
| الشعار | (406, 50) — 157 × 36 pt |
| الجدول | 5 حدود رأسية متساوية بدءاً من x=58.1 |
| الخط | Almarai (Regular/Bold) |

> الفرق المتوسط في مواضع النصوص عن النموذج الأصلي: **< 1.5 pt**.

---

## 🔐 متغيرات البيئة على Vercel

| المتغير | الوصف |
|---|---|
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_KEY` | مفتاح service_role (سري) |
| `SECRET_KEY` | مفتاح تشفير جلسات Flask |
| `PUBLIC_BASE_URL` | رابط الموقع العام (اختياري) |

---

## 📜 الترخيص

MIT © 2026
