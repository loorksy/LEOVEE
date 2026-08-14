# تقرير جاهزية الإنتاج (2026-08-14)

تدقيق موازٍ بستة محاور (إعدادات، نشر، أمان متبقٍ، بيانات/ذاكرة، مراقبة، واجهة)، ثم
إصلاح كل ما يكسر أو يسرّب أو ينهار في نشر حقيقي خلف وسيط عكسي. **1240 اختبار خلفية +
106 واجهة، mypy strict وruff نظيفان، الترحيل يصعد وينزل، الواجهة تُبنى.**

## Blockers أُصلحت

| العَرَض في الإنتاج | الإصلاح |
|---|---|
| **كل مهام التضمين تنهار**: `memory_embeddings.embedding_json` عمود `NOT NULL` بلا كاتب — كل إدراج يرمي IntegrityError، فتموت فهرسة الذاكرة والبحث الدلالي | هجرة `025` تُسقط العمود الميت (لا مرجع له في الكود) |
| **ذاكرة الحالات فارغة أبداً**: لا كاتب إنتاجي لـ`market_cases` — أدوات «متى بدا الذهب هكذا من قبل» تعيد لا شيء دائماً | مهمة arq `market_case_index_job` (ليلياً، محدودة، idempotent) + `indexer.py` |
| **انكشاف عام**: `docker-compose.prod.yml` يترك Postgres/Redis على `0.0.0.0` (منافذ Docker تتجاوز UFW) | `ports: !reset []` + volume دائم لـRedis + حدود موارد (وكيل النشر) |
| **حدّ المحاولات عالمي خلف الوسيط**: `TRUST_PROXY_HEADERS` غير مضبوط ولا مفروض ولا يعبر PROXY protocol عبر nginx→Caddy | فرض في `validate_production_startup` + إصداره في المولّد + `proxy_protocol` على nginx وCaddy |
| **لا مسار إنتاج يضبط `ENVIRONMENT=production`** فتموت كل حرّاس الإقلاع | (موثَّق أدناه — يحتاج مولّد بيئة إنتاج؛ الحرّاس نفسها صارت أقوى وتُفحص) |

## عالية/متوسطة أُصلحت (كود)

- **العزل يُتحقَّق فعلياً عند الإقلاع**: `verify_runtime_db_role` يُستدعى في lifespan للـAPI وMCP وفي `on_startup` للعامل — دور superuser/BYPASSRLS يرفض الإقلاع بدل تجاوز RLS صامتاً.
- **`validate_production_startup` صار يفرض**: `TRUST_PROXY_HEADERS`، طول `SECRET_KEY` ≥32 (أرضية HS256)، `OANDA_EXECUTION` مطفأ (في كل البيئات)، `CORS_ORIGINS` ليست `*` ولا localhost، ودور `leovee_app` بتحليل الـURL لا بالمطابقة النصية.
- **`/health/ready` يعيد 503 عند التدهور** لا 200، فيُسحب المثيل من التدوير.
- **حدّ المحاولات Redis**: تجمّع اتصال واحد + نافذة ذرّية (Lua) — أُزيل خطر القفل الدائم بمفتاح بلا TTL.
- **ذاكرة noise صامتة**: البديل الحتمي للتضمين (بلا مزوّد) يسجّل تحذيراً ويرفع عدّاد `embedding_fallback_total`.
- **كاردينالية المقاييس**: التوسيم بقالب المسار المطابق و`__unmatched__` للبقية — زاحف عدائي لا يفجّر السلاسل.
- **فشل مهام العامل مرئي**: `on_job_end` يرفع `worker_job_failures_total{job,code}`.
- **Sentry**: أُضيف `sentry-sdk` كتبعية، والتهيئة تصرخ إن ضُبط DSN والحزمة غائبة، و`include_local_variables=False`.
- **تنقيح السجل**: أُضيفت أنماط `lvk_` وJWT.
- **مقارنة رمز `/metrics`** بـ`secrets.compare_digest`.
- **الواجهة**: `ErrorBoundary` علوي يمنع الشاشة البيضاء؛ `index.html` صار `lang="ar" dir="rtl"` فلا وميض اتجاه.
- **النشر (وكيل)**: `stop_grace_period: 30s`، healthcheck على `/health/ready`، healthcheck للعامل، CSP `worker-src blob:` لعمّال TradingView.

## متبقٍ — إجراءات مالك/عمليات (ليست كوداً)

- **مولّد بيئة إنتاج**: المولّد الحالي يثبّت `ENVIRONMENT=staging`. الإنتاج يحتاج مساراً يصدر `ENVIRONMENT=production` (عندها تُفعَّل الحرّاس الجديدة كلها). قرار نشر.
- **ثنائيات TradingView (LFS)**: مازالت محجوبة بالميزانية — صفحة الشارت «متدهورة معروفة» حتى ترفعها.
- **تثبيت صور الأساس بالـdigest**، ومصدر مقاييس مستقل للعامل (endpoint/pushgateway)، وحوافّ nginx المتعددة إن كان المضيف مشتركاً (موثّق في `setup_vps_edge_nginx.sh`).
- **بندان أمنيان كامنان** (من `SECURITY_AUDIT.md`) ما زالا آمنين اليوم: نمط scope-from-argument في خط التعلّم، ومصادقة مفاتيح API الميتة.

المرجع الكامل للنتائج: تدقيق الجلسة (٦ محاور).
