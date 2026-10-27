# ربط النطاق `ajeer.qiwa.sa` بالمنصة

## الوضع الحالي
- النطاق `ajeer.qiwa.sa` **مسجَّل ومستضاف بالفعل** (السيرفرات: `ns1.bluvalt.sa` / `ns2.bluvalt.sa`، العنوان `185.118.121.89`) ويعرض موقعاً قائماً.
- أُضيف النطاق إلى مشروع Vercel (`prj_shxDHaFIPwDab8OIDHMqF6emV5UD`) وأصبح في حالة **incomplete / misconfigured** بانتظار تعديل الـ DNS فقط.
- التطبيق صار **يتكيّف مع أي نطاق**: بمجرد أن يصل النطاق إلى Vercel ستتحوّل كل روابط التحقق ورمز QR وملف PDF تلقائياً إلى
  `https://ajeer-qiwa-sa-app.vercel.app/verify/?id=…` دون أي تعديل في الكود.

## المطلوب لتشغيله (دقيقتان في لوحة الاستضافة)
عند مزوّد الاستضافة الذي يتحكّم بـ `qiwa.sa` (بلوفالت):

| النوع | الاسم | القيمة | TTL |
|---|---|---|---|
| CNAME | `ajeer` | `a8320eb305c4d766.vercel-dns-017.com.` | 300 |

أو (بديل):

| النوع | الاسم | القيمة | TTL |
|---|---|---|---|
| A | `ajeer` | `76.76.21.21` | 300 |

> لا تحذف أي سجل آخر. السجل الحالي `ajeer → 185.118.121.89` هو الذي يجب استبداله.

## التحقق بعد التعديل
```bash
curl -I https://ajeer.qiwa.sa/        # يجب أن يظهر x-vercel / server: Vercel
curl -I https://ajeer.qiwa.sa/login   # 200
```
وسيُصدر Vercel شهادة SSL تلقائياً خلال دقائق.

## البديل إن لم يكن الوصول للـ DNS متاحاً
1. نطاق تملكه أنت (أي اسم) → أعطني سجل CNAME وأربطه فوراً.
2. أو تفعيل وكيل عكسي على الاستضافة الحالية (LiteSpeed) عبر `.htaccess`:
```apache
RewriteEngine On
RewriteRule ^(.*)$ https://ajeer-qiwa.vercel.app/$1 [P,L]
```
لكن هذا يُبقي الأداء أبطأ ولا يدعم WebSocket، والأفضل تعديل الـ DNS.

## النطاقات العاملة الآن
| النطاق | الحالة |
|---|---|
| `https://ajeer-qiwa-sa-app.vercel.app` | **النطاق الأساسي (Canonical)** — كل الكلمات مفصولة بشرطة `-` ولا كلمة ملتصقة |
| `https://ajeer-qiwa-sa-app.vercel.app/ajeer.qiwa.sa/l` | **الرابط الرسمي للمنصة** — صفحة الهبوط بالنقاط الحقيقية |
| `https://ajeer-qiwa-sa-app.vercel.app/ajeer.qiwa.sa/verify/?id=…` | رابط التحقق ورمز QR |
| `https://ajeerqiwaapp.vercel.app` | يعمل (الاسم السابق، ملتصق الكلمات) |
| `https://ajeer-qiwa.vercel.app` | يعمل (اختصار) |
| `https://ajeer.qiwa.sa` | معلّق — ينتظر تعديل الـ DNS فقط |

### مسار النقاط (Dotted path)
وسيط `_DottedAlias` في `backend/app.py` يخدم البادئتين `/ajeer.qiwa.sa/…` و `/ajeer.qiwa/…`
بإزالة البادئة من `PATH_INFO` قبل تمرير الطلب لتطبيق Flask، لذا:

- `…/ajeer.qiwa.sa/l` → صفحة الهبوط
- `…/ajeer.qiwa.sa/verify/?id=…` → صفحة التحقق
- `…/ajeer.qiwa.sa/login` → تسجيل الدخول

### قواعد التحويل التلقائي (المرحلة 9 — التحديث الأخير)
كل زيارة لا تعرض بيانات حقيقية تُحوَّل فوراً (`302`) إلى الموقع الرسمي `https://ajeer.qiwa.sa/`
**بدون عرض أي صفحة أو تفاصيل على المنصة**:

| الحالة | النتيجة |
|---|---|
| النطاق بلا مسار `/` | `302` → `https://ajeer.qiwa.sa/` |
| أي مسار غير موجود (`/nope`, `/wp-admin`, …) | `302` → `https://ajeer.qiwa.sa/` |
| `/l` و `/landing/` (مسارات الهبوط القديمة) | `302` → `https://ajeer.qiwa.sa/` |
| `/verify/` بلا رمز | `302` → `https://ajeer.qiwa.sa/` |
| رمز تحقق غير صحيح أو تصريح غير موجود | `302` → `https://ajeer.qiwa.sa/` |
| تصريح صحيح (رمز 64 محرفاً) | صفحة التحقق تُعرض (200) |

- لوحة التحكم على `/dashboard` (كانت على `/`)، والدخول عبر `/login`.
- الثابت `OFFICIAL_HOME_URL` في `backend/app.py` هو مصدر وجهة التحويل الوحيد.
