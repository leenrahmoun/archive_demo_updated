# الدراسة التصميمية - مرجع عملي للمشروع

هذا الملف يلخص المرجع الأساسي `الدراسة التصميمية الكاملة.pdf` بصيغة قابلة للتطوير.

## 1) نطاق النظام

- نظام إدارة أضابير ووثائق رقمية.
- الإضبارة تمثل بيانات الموظف الثابتة + الموقع الفيزيائي.
- الوثيقة تمثل حدثا إداريا مرتبطا بإضبارة عبر `dossier_id`.
- يمنع تكرار بيانات الموظف داخل جدول الوثائق.

## 2) الأدوار

- `admin`: إدارة كاملة + إجراءات استثنائية + سجل العمليات.
- `data_entry`: إدخال/تعديل/إرسال وثائق قبل الاعتماد.
- `auditor`: مراجعة pending ثم اعتماد أو رفض مع سبب.
- `reader`: بحث وعرض/تحميل الوثائق المعتمدة فقط.

## 3) دورة حياة الوثيقة

- الحالات: `draft`, `pending`, `approved`, `rejected`.
- انتقالات أساسية:
  - `draft -> pending` بعد اكتمال الحقول والملف.
  - `pending -> approved` بواسطة auditor/admin.
  - `pending -> rejected` مع `rejection_reason`.
  - `rejected -> pending` بعد التصحيح وإعادة الإرسال.
- الحذف منطقي فقط `is_deleted=true`.

## 4) قواعد العمل الأساسية

- لا يسمح بإنشاء إضبارة بدون وثيقة أولى.
- لا يسمح إطلاقا بوجود إضبارة فارغة في قاعدة البيانات.
- لا حفظ تلقائي؛ الحفظ صريح فقط.
- تعديل `pending` غير مسموح.
- تعديل `approved` مسموح استثنائيا لـ `admin` فقط.
- `data_entry` يحذف منطقيا الوثيقة `draft` فقط.

## 5) المتطلبات التقنية المؤكدة

- Frontend: React SPA + Vite + React Router + TanStack Query.
- Backend: Django + DRF + SimpleJWT.
- Database: PostgreSQL 15+.
- الملفات: PDF فقط.
- حجم الملف: حد أدنى 100KB وحد أقصى 15MB.
- التخزين: Folder Sharding على `dossier_id`.

## 6) بنية التخزين

المسار النهائي:

`/archive/{L1}/{L2}/{dossier_id}/{doc_type_ar}_{doc_id}.ext`

أمثلة:

- `id=123456 -> /archive/12/34/123456/تعيين_قرار_987654.pdf`
- `id=1 -> /archive/00/00/000001/تعيين_قرار_1.pdf`

## 7) تصميم البيانات (موجز)

- `users`: حسابات النظام والأدوار.
- `dossiers`: هوية الإضبارة وبيانات الموظف والموقع.
- `documents`: بيانات الوثيقة والملف والحالة والتدقيق.
- `document_types`: 59 نوعا ضمن 7 مجموعات.
- `governorates`: قوائم المحافظات.
- `audit_log`: سجل عمليات create/update/submit/approve/reject/delete/restore.

## 8) قيود قاعدة البيانات

- `dossiers.file_number` فريد.
- `dossiers.national_id` فريد.
- `documents.file_path` فريد.
- Partial Unique للوثائق غير المحذوفة:
  - `(dossier_id, doc_type_id, doc_number) WHERE is_deleted = FALSE`.

## 9) واجهات النظام

- واجهة إدخال بيانات عملية ومباشرة (بدون لوحة تحليلية في النسخة الأولى).
- واجهة تدقيق لقائمة `pending` (الأقدم أولا).
- واجهة مدير للنظام والتدخلات الاستثنائية.
- واجهة قارئ للعرض والتحميل فقط للمعتمد.

## 10) API أساسية

- Auth: login/refresh/logout/me.
- Dossiers: list/create/detail/update.
- إنشاء الإضبارة عبر API يتطلب وثيقة أولى داخل نفس الطلب.
- تنفيذ إنشاء الإضبارة + الوثيقة الأولى يتم في service/API layer ضمن معاملة ذرية واحدة (atomic transaction) مع rollback كامل عند فشل إنشاء الوثيقة.
- Documents: create/update/submit/approve/reject/delete/restore/file.
- Lookup: document types + governorates.
- Audit queue.
- Admin users management.

