# خطة ترحيل AiChart (Lonora) إلى Leovee

## 1. السياق (Context)

`loorksy/AiChart` — الاسم الداخلي **Lonora** — منصة تداول فوركس/ذهب ناضجة تعمل في الإنتاج:
**≈ 196,600 سطر TypeScript** في `src/` + خادم MCP مستقل (68 أداة) + 169 مسار API + 68 جدولاً.

`loorksy/leovee` — إعادة بناء نظيفة لنفس المنتج على معمارية مختلفة: **FastAPI + SQLAlchemy 2 +
Alembic + Postgres/pgvector + Redis/arq + React/Vite**. حجمها اليوم ≈ 18.8k سطر Python و6.5k
سطر TS/TSX، مع 16 هجرة و25 راوتر.

**المشكلة:** `LEOVEE_SPEC.md` كُتب صراحةً كمشروع **greenfield** — «لا يوجد نظام قديم للترحيل، لا تنتج
خطط ترحيل». فبُني Leovee بمعمارية سليمة جداً لكن **محرّكاته فارغة**. طبقة `backend/app/engines/`
مجموعها **656 سطراً** من العناصر النائبة. هذا `backend/app/engines/zones.py` حرفياً:

```python
mid   = (bars[-1].high + bars[-1].low) / 2
width = (bars[-1].high - bars[-1].low) * 2
zones = [{"type": "DEMAND", "low": mid - width, "high": mid, "strength": 0.5}, ...]
```

منطقة عرض ومنطقة طلب مختلَقتان من شمعة واحدة بقوة ثابتة. و`structure.py` (16 سطراً) يحدّد الانحياز
بمقارنة أول إغلاق بآخر إغلاق. هذه ليست محرّكات — توقيعات دوال صحيحة بأجساد فارغة.

**الهدف:** نقل المعرفة والمنطق من AiChart إلى Leovee — إعادة كتابتها بـ Python داخل معمارية Leovee —
حتى التكافؤ الوظيفي كمنصة **تحليل وتوصيات فقط**.

---

## 2. قرارات المالك (مُثبَّتة — تحكم كل ما يليها)

| # | القرار | الأثر |
|---|--------|-------|
| D1 | **إعادة كتابة المنطق داخل Leovee** — معمارية Leovee نهائية، AiChart مرجع | لا يُنقل سطر TS كما هو إلى الخلفية |
| D2 | النطاق: كل المنتج حتى التكافؤ الوظيفي | 12 مرحلة |
| D3 | **MetaAPI / MT5 / ربط حساب وسيط — خارج النطاق نهائياً** | يسقط ~14 جدولاً و~35 مساراً |
| D4 | **تنفيذ الصفقات — خارج النطاق** | منصة تحليل وتوصيات فقط |
| D5 | **تليجرام وكل الإشعارات الخارجية — خارج النطاق** | يبقى بريد التحقق/استعادة كلمة المرور فقط |
| D6 | **عقيدة القرار: عقيدة AiChart — اتجاه دائماً** | كل تحليل ناجح ⇐ BUY أو SELL مع خطة كاملة. `NO_TRADE` للأعطال التشغيلية فقط |
| D7 | **لا باكتيست ولا تحقق إحصائي من الأساس** | تُلغى `research-service/` بكاملها (12,789 سطراً) وكل ما يعتمد عليها |
| D8 | **الدستور يُعاد كتابته من الصفر لـ Leovee** | لا يُنقل `SYSTEM.md` نصّاً؛ يُستخدم مرجعاً |
| D9 | **TradingView Advanced Charts — لا KLineChart** — ومُضمَّنة داخل النظام لا تُجلب وقت البناء | انحراف موثَّق عن `LEOVEE_SPEC §43` |
| **D10** | **الذهب فقط — XAUUSD.** المنصة والوكيل والتحليل وكل شيء | كون الرموز صار رمزاً واحداً؛ ADR 0007 |

### تفكيك D6 — ماذا تعني «اتجاه دائماً» عملياً

ثلاث طبقات منفصلة في كل نتيجة، لا تُخلط أبداً:

1. **الرأي التحليلي** — BUY أو SELL. لا ثالث لهما.
2. **نوع الخطة** — فورية / استباقية / شرطية.
3. **حالة التنفيذ** — صالحة الآن / بانتظار التفعيل / منتهية / مُبطَلة / محجوبة.

`NO_TRADE` ليس رأياً تحليلياً — هو **عطل تشغيلي** له سبب مُسمّى (بيانات ناقصة أو بائتة، محرّك فشل،
مزوّد LLM غير متاح). هذا يتوافق تماماً مع عقد Leovee القائم `fail_closed_no_trade(reason)` في
`backend/app/agents/orchestrator.py` — نحتفظ به كما هو، ونعيد تسمية دلالته في الواجهة من «لا صفقة»
إلى «تعذّر إكمال التحليل: <السبب>».

**تعارض يجب حلّه في M4:** `LEOVEE_SPEC §110` (خطوة 17) يطلب توليد سيناريو «لا صفقة» إلى جانب الصاعد
والهابط، و`RecommendationDirection.NO_TRADE` مُعرَّف كاتجاه قرار. يُعدَّل `engines/scenario.py` ليولّد
سيناريوهين اتجاهيين + سيناريو **إبطال** (ما الذي يُسقط الأطروحة)، لا سيناريو امتناع. ويُقيَّد
`NO_TRADE` في الـ enum بأن يكون قابلاً للإنتاج من مسار fail-closed وحده — يُختبَر صراحةً.

### تفكيك D7 — ما الذي يسقط بالضبط

| يسقط | يبقى |
|------|------|
| `research-service/` بكاملها (محرك باكتيست، walk-forward، bootstrap، Monte Carlo، تحليل حساسية، سرب أبحاث، 35 ملف pytest) | **وكيل بحث الأخبار والأساسيات** (`LEOVEE_SPEC §26/§27`) — مصدر أدلة حيّ، لا باكتيست |
| `src/lib/strategies/{backtestCapital,catalogGen}.ts` والأدلة المشتقة من الباكتيست في `evidence.ts` | إحصاءات الاستراتيجيات المشتقة من **النتائج الحقيقية** للتوصيات المغلقة (`strategy_stats`) |
| `src/lib/tradingDna/backtestEvidence.ts`، `shadowTrader.ts` | تحليلات DNA السلوكية من التوصيات الفعلية |
| `backend/app/api/routes/replay.py` كأداة تحقق إحصائي | إعادة العرض كأداة **مراجعة بصرية** لتحليل سابق (تبقى، وتحافظ على `test_replay_temporal_s101.py`) |

**النتيجة المباشرة:** «الدعم الإحصائي» في التوصية لم يعد يأتي من باكتيست، بل من حلقة التعلّم على
النتائج الحقيقية (M8). وهذا يطابق بند الدستور: *لا تدّعِ دعماً إحصائياً لا تملكه* — وقبل تراكم عيّنة
كافية، تُنشر التوصية صراحةً كـ **«تحليل مباشر بلا دعم إحصائي»**.

### تفكيك D9 — طبقة الشارت

هذا القرار **يلغي أخطر إعادة كتابة في الواجهة** ويقلب اقتصاد المرحلة رأساً على عقب:

- محوّلات AiChart لـ TradingView تصبح **قابلة للنقل TS → TS** بدل أن تُرمى:
  `src/lib/chart/tv/{tvDatafeed,tvDrawingAdapter,tvStudyAdapter,tvUserDrawings,spreadPriceLines}.ts`
  و`src/components/chart/TvChart.tsx` (675 سطراً). التحويل الوحيد: Next.js/React 19 → Vite/React 18
  (إزالة `"use client"`، تبديل `next/dynamic` بـ `React.lazy`، تبديل مسارات `@/`).
- مفردات الرسم الـ24 نوعاً دلالياً والـ18 دوراً في `src/lib/chartDrawings.ts` تنتقل **بمحوّلها الجاهز
  والمُختبَر**، بدل بناء 24 عارضاً جديداً من الصفر على KLineChart.
- تُحذف تبعية `klinecharts` وملفات `frontend/src/chart/{KLineChartAdapter,ChartDataAdapter}.ts`.
- **يبقى** `frontend/src/chart/ChartTypes.ts` — واجهة `ChartEngine` المحايدة عن العارض هي العقد،
  ونستبدل التنفيذ تحتها فقط. هذا ما يجعل القرار رخيصاً.

**«من نفس النظام وليس يجلب وقت البناء»:** تُلتزم مكتبة `charting_library` داخل مستودع Leovee
(`frontend/vendor/tradingview/` + الأصول الساكنة في `frontend/public/charting_library/`)، ويُحذف
سكربت الجلب `scripts/provision-tradingview.mjs` ومتغيّرا `TRADINGVIEW_LIBRARY_URL/TOKEN`. البناء
يصبح مكتفياً ذاتياً بلا مصدر خارجي خاص.

> **تحفّظان يجب أن تعرفهما قبل التنفيذ — ثم القرار قرارك:**
> 1. **الترخيص.** ترخيص TradingView Advanced Charts يمنع إعادة التوزيع العلني. الالتزام في مستودع
>    **خاص** مقبول عادةً؛ لكن إن صار `loorksy/leovee` عاماً يوماً ما تصبح المكتبة مكشوفة. الخطة تفترض
>    بقاء المستودع خاصاً، وتضيف حارساً في CI يفشل إن تغيّرت الرؤية.
> 2. **حجم المستودع.** ‏≈27 ميجابايت من الأصول الثنائية في git. مقبول، لكن يُنصح بـ Git LFS للمجلد
>    لتفادي تضخّم تاريخ الاستنساخ. سأستخدم LFS ما لم تطلب خلاف ذلك.
>
> وكلاهما يستوجب تعديل `LEOVEE_SPEC §43` و`ARCHITECTURE.md` — إبقاء الوثيقة تقول KLineChart بينما
> الكود يقول TradingView هو بالضبط نوع الانحراف الذي أنتج هذه الفجوة أصلاً.

---

## 3. القرار المعماري — ما يُحفَظ من Leovee بلا مساس

**ننقل الذكاء إلى العزل، لا العزل إلى الذكاء.**

تعدّد المستأجرين في AiChart = عمود `user_id` + شرط `WHERE` يدوي في كل استعلام، بلا RLS وبلا كيان
منظمة/مساحة عمل. Leovee يملك عزلاً على مستوى قاعدة البيانات. هذا الأصل وحده يبرّر اتجاه الترحيل.

| الأصل | الملفات |
|-------|---------|
| **عزل RLS حقيقي** — `FORCE ROW LEVEL SECURITY` على 18+ جدولاً بسياسات على `app.tenant_id`/`app.workspace_id` | `backend/alembic/versions/005_learning_rls_candles.py` (`RLS_WORKSPACE_TABLES` + `_workspace_rls_policy()`) |
| فرض دور قاعدة بيانات غير متجاوز للـ RLS | `app/infrastructure/database.py` (يرفض أي اتصال بغير `leovee_app`، ويؤكد `NOT rolsuper AND NOT rolbypassrls`) |
| ربط سياق المستأجر | `app/infrastructure/rls.py` (افتراضي deny-all)، `app/api/deps.py::get_workspace_context` (يتحقق من العضوية في القاعدة ولا يثق بالترويسة)، `app/core/tenant_rls.py::bind_workspace_rls` (للعمّال وSSE وMCP) |
| هرمية organizations → workspaces → members + RBAC | `app/models/{organization,workspace,rbac}.py` |
| موجّه النماذج + تدوير نماذج OpenRouter المجانية | `app/providers/llm/{router,openrouter,openrouter_catalog,factory}.py` |
| بث SSE مع failover أثناء البث | `app/services/chat_stream.py` |
| **عقد fail-closed** | `app/agents/orchestrator.py::fail_closed_no_trade` |
| هجرات Alembic (16، سلسلة خطية، مع اختبار up/down) | `backend/alembic/versions/` |
| عمّال arq (11 مهمة، 8 جدولة) | `app/workers/settings.py` |
| CI (ruff + mypy strict + pytest على pgvector + فحص تسريب الأسرار) ونشر staging عبر Caddy | `.github/workflows/`، `scripts/` |
| تجريد الشارت خلف `ChartEngine` | `frontend/src/chart/ChartTypes.ts` |

---

## 4. ما لا يُرحَّل (استبعاد صريح، لا إهمال)

| المستبعَد | مصدره في AiChart | السبب |
|-----------|------------------|-------|
| MetaAPI بكامله | `src/lib/metaapi/`، `brokers/metaApiAdapter.ts` | D3 |
| MT5 (الجسر المحلي والسحابي) | `src/lib/mt5/`، `mt5local/`، `brokers/`، `infra/mt5/`، 20 مسار `api/agent/mt/*` | D3 |
| تنفيذ الصفقات بكل مساراته | `execution.ts` (31KB)، `executionSafety.ts`، `executionKillSwitch.ts`، `approvalFlow.ts`، `orderPlan.ts`، `tradeClose.ts`، `agents/executionGuardAgent.ts`، `recommendations/{autoExecutor,tradeManagement}.ts` | D4 |
| تليجرام | `telegram*.ts` (5 ملفات)، `telegram-ar-commands.json`، `api/telegram/*` | D5 |
| Web Push والبريد كقناة إشعار | `push.ts`، `public/push-sw.js`، `notifyTrade.ts`، `dailySummary.ts`، `weeklyReport.ts`، `recommendations/lifecycleNotifier.ts` | D5 |
| ربط حساب الوسيط | `mtConnectFlow.ts`، `forexConnection.ts`، `api/mt5/brokers` | D3 |
| **الباكتيست والتحقق الإحصائي بكامله** | `research-service/` (12,789 سطراً)، `src/lib/research/`، `strategies/backtestCapital.ts`، `tradingDna/{backtestEvidence,shadowTrader}.ts`، `api/backtests/*` | D7 |
| طبقة البيانات المكتوبة يدوياً | `db/sqlite.ts` (98KB)، `db/pg.ts` (97KB)، `db/sql.ts` (مترجم لهجة SQL بالتعبيرات النمطية) | Leovee يستخدم SQLAlchemy + Alembic |
| الكائن الإلهي | `src/lib/store.ts` (50KB / 90 تصدير) | يُفكَّك إلى خدمات، لا يُنقل |
| خادم MCP كـ runtime | `mcp/` (Node/Express) | تُنقل **تعريفات** الأدوات فقط؛ Leovee يخدمها من Python |
| المصادقة والفوترة والأدمن | `src/lib/{auth,billing,subscription,admin}/` | نسخ Leovee أفضل (RLS + RBAC + argon2) |
| سكربتات عابرة (~60 ملف `pr63-*`/`pr66-*`/`tmp-*`) ومسارات `web/` القديمة | `infra/`، README/CI/PM2/compose | مخلّفات، ومعطوبة أصلاً في شجرة AiChart |
| مرجع اختبار ميت | `src/lib/candles/__tests__/warmDemand.test.ts` في `package.json` | المجلد محذوف منذ `e87174d` |

**حدّ دقيق — لا تخلط بين شيئين:**
- `agents/executionGuardAgent.ts` كـ**مرحلة** يسقط. لكن **حسابه** لا يسقط: خطة يقع وقفها داخل السبريد
  الحيّ، أو ينهار عائدها/مخاطرتها بعد التكاليف، هي **توصية سيئة** بصرف النظر عن وجود تنفيذ. تُنقل هذه
  الفحوص إلى `backend/app/engines/plan_sanity.py` (اسم جديد)، ويُحذف كل ما يمسّ أمراً.
- `models/trade.py` و`routes/trades.py` في Leovee **يبقيان**، بإعادة توصيف: **سجل يدوي لتنفيذات
  يُبلّغ عنها المستخدم بنفسه**، يغذّي تعلّم النتائج. لا مسار تنفيذ. `test_trade_execution_gate.py` هو
  الضمانة المكتوبة لذلك.

---

## 5. استراتيجية النقل TypeScript → Python: اختبار تفاضلي بمرجع ذهبي

أخطر نقطة في المشروع. إعادة كتابة آلاف الأسطر من الهندسة الحتمية «بالقراءة والفهم» تنتج انحرافاً
صامتاً: الكود يعمل، والأرقام مختلفة، ولا أحد يلاحظ حتى تخرج توصية خاطئة.

**لا نثق بالقراءة — نثبّت المخرجات.** المنطق الحتمي في AiChart دوالّ نقية، مثل
`src/lib/chart/geometry/detectGeometry.ts::detectChartGeometry(input) → GeometrySnapshot`.

**الإجراء لكل محرّك:**

1. **تثبيت عيّنات مرجعية** — شموع OANDA حقيقية عبر 20 رمزاً × 4 أطر × 5 نوافذ، **إضافةً إلى** بُناة
   الشموع الاصطناعية الموجودة أصلاً في اختبارات AiChart (مثل `trend()`/`candle()` في
   `candlesticks.test.ts`) — هذه كُتبت خصيصاً لتثبيت الحالات الحدّية وتنتقل إلى pytest بترجمة شبه معدومة.
   تُحفظ في `backend/app/tests/fixtures/candles/`.
2. **توليد المرجع الذهبي** — سكربت `tsx` عابر داخل شجرة AiChart يستورد الوحدات النقية ويكتب
   `golden/<engine>/<fixture>.json`. يُنفَّذ **مرة واحدة**؛ تُلتزم المخرجات في Leovee. شجرة AiChart لا
   تُعدَّل ولا تُدفع، وLeovee لا يعتمد على Node في CI ولا في التشغيل — فقط على JSON الملتزَم.
3. **نقل الدالة بحرفية التدفق** — لا «تحسين» أثناء النقل. أي تحسين سلوكي يأتي في التزام منفصل **بعد**
   خضرة الاختبار الذهبي.
4. **اختبار تفاضلي** بسياسة تفاوت مكتوبة في `docs/PORTING.md`:
   - **تطابق تام** للمخرجات المنفصلة: نوع النمط، الاتجاه، `status`، `stage`، `broken`، فهرس المحور،
     وطول المصفوفة **وترتيبها**.
   - `math.isclose(rel_tol=1e-9)` للأسعار المشتقّة حسابياً.
   - أي شيء يحتاج تفاوتاً أوسع من `1e-9` هو **خطأ نقل**، لا حالة تفاوت.
5. **فروق مقصودة** تُوثَّق في الاختبار بسبب مكتوب — لا تُطمَس بتوسيع التفاوت.

**أربعة مصائد JS→Python تُوقِع كل مرة** (تُعالَج مركزياً في `backend/app/core/numeric.py`):

| المصيدة | JS | Python |
|---------|-----|--------|
| `%` على السالب | يقتطع نحو الصفر | يقرّب نحو ‎−∞‎ |
| `Math.round` | نصف لأعلى نحو ‎+∞‎ | مصرفي (نصف للزوجي) |
| `Array.sort` | مقارن نصّي افتراضي، استقرار مضمون منذ ES2019 | يتطلب `key=` صريحاً |
| `JSON.stringify` | يسقط مفاتيح `undefined` | يجب إسقاط `None` قبل المقارنة |

**سياسة الأنواع العددية (قرار حاسم قبل أي نقل):** الهندسة والمؤشرات والبنية والسيولة والمناطق والنظام
السوقي تعمل على `float` (‏IEEE-754 مطابق بتّياً لـ `Number` في JS). ‏`Decimal` يبقى عند حدّ المال فقط:
حفظ أسعار الدخول/الوقف/الأهداف، وحساب حجم المخاطرة. **هذا يستوجب تغيير `backend/app/engines/volatility.py::OHLCBar`
من `Decimal` إلى `float` قبل نقل أي محرّك** — وإلا انحرفت كل عيّنة ذهبية و«أُصلحت» بتفاوتات تخفي أخطاءً حقيقية.

**حاجز إضافي مكتشَف:** `OHLCBar` الحالي يحمل `open/high/low/close` **بلا طابع زمني وبلا حجم**، بينما
`bars_from_candles` في `orchestrator.py` يُسقط الطابع الزمني. وكل تعليق على الشارت يحتاج مرساة
`{ts, price}`. توسيع `OHLCBar` بـ `ts` و`volume` شرط مسبق للمرحلة M2 كلها، ويمسّ كل محرّك والمايسترو.

**ما لا يخضع لهذه الطريقة:** كل ما يستدعي LLM (المُقرِّر النهائي، خصم الشيطان، كاتب الذاكرة). لا مرجع
ذهبي لمخرَج احتمالي — يُختبَر بسيناريوهات مرجعية على غرار `test:decision-authority` في AiChart
(سيناريو سوق ← القرار المسموح)، لا بمطابقة نصية.

---

## 6. المراحل

**آلية البقاء أخضر في كل مرحلة:** عقد fail-closed هو صمّام الأمان. Leovee نصف المُرحَّل يعيد
`NO_TRADE` بسبب صادق بدل توصية مختلَقة — فيبقى قابلاً للنشر عند كل حدّ مرحلة، وكل مرحلة **تقلّص**
مجموعة المدخلات التي تتدهور.

**مسارات متوازية بعد M0:**
`المسار أ (القيمة الحتمية)`: M1 → M2 → M3 → M4 → M6 → M7 → M8 ·
`المسار ب (بنية LLM)`: M5 (يبدأ فوراً بعد M0، يجب أن يهبط قبل M6) ·
`المسار ج (الواجهة)`: M9 (يحتاج مخرجات M4) و M10 (سقالته في M0)

---

### M0 — الحواجز والعقود ونزع الأنياب

**الهدف:** جعل نقل خطأ عزل مستحيلاً، ونقل كود تنفيذ مستحيلاً، وقبول نقل رقمي خاطئ مستحيلاً. ووقف
كذب المنتج بشأن المناطق.

**جديد:**
- `backend/app/tests/conformance/test_rls_coverage.py` — اختبار **مولَّد**: يمشي على بيانات SQLAlchemy
  الوصفية؛ كل جدول فيه `workspace_id` يجب أن يكون له `rowsecurity` و`relforcerowsecurity` وسياسة
  `%_workspace_isolation` في `pg_policies`. وكل جدول بلا `workspace_id` يجب أن يظهر في قائمة سماح
  صريحة `PLATFORM_GLOBAL_TABLES` (الرموز، الخطط، `model_configs`، كتالوج المطالبات، أطلس الأنماط).
  **غياب `workspace_id` يصبح قراراً، لا سهواً** — ويغطي مجاناً كل الجداول التي ستضيفها المراحل التالية.
- `backend/app/tests/conformance/test_two_workspace_isolation.py` — مُعامَل على البيانات الوصفية نفسها:
  صفّ في مساحة A، ربط مساحة B، تأكيد صفر نتائج، وتأكيد أن الإدراج بـ `workspace_id` غريب يرمي.
- `backend/app/tests/conformance/test_no_execution_surface.py` — حارس بحث نصّي على `backend/`
  و`frontend/src/` يفشل عند: `metaapi`، `mt5`، `place_order`، `send_order`، `broker_login`،
  `telegram`، `webpush`، `backtest`. يجعل قائمة الاستبعاد **آلية** طوال المشروع.
- `backend/app/core/numeric.py` — سياسة §5 في كود: `to_float_bars()`، `js_round()`، `js_mod()`.
- **منصّة المرجع الذهبي**: `backend/app/tests/fixtures/golden/` + `backend/app/tests/golden.py`
  (محمّل ومقارن ينفّذ سياسة التفاوت)، و`docs/PORTING.md`.
- `frontend/src/i18n/{index,ar,en}.ts` + معالجة `dir` + اختبار تكافؤ مفاتيح — **السقالة فقط**، بشكلها
  المنقول من `src/lib/i18n/`. السبب: كل مكوّن يُبنى في M9–M10 يولد مترجَماً؛ التحديث الرجعي في M10.
- `docs/adr/` — قرار معماري موثَّق لكل بند من D6–D9.

**مُعدَّل:**
- الاثنا عشر محرّكاً النائبة تُعيد `{"status": "unavailable", "reason": "ENGINE_NOT_IMPLEMENTED"}`
  بدل أرقام مختلَقة، و`orchestrator.py` يقصّرها إلى `fail_closed_no_trade("ENGINE_UNAVAILABLE", detail=<engine>)`.
  **المنتج يصير أصدق في اليوم الأول**، وكل مرحلة بعدها تحسّن رتيب صارم.
- `OHLCBar`: `Decimal` → `float`، وإضافة `ts` و`volume`.

**مخاطر:** اختبار تغطية RLS سيفشل يوم إطلاقه على جداول قائمة (`agent_traces` له سياسة عبر الأب،
`candles` مقسَّم وعالمي). خصّص وقتاً لتسوية ~5 استثناءات في قائمة السماح بمبرّر مكتوب لكلٍّ منها.

**معايير الخروج:** `pytest backend/app/tests/conformance/` أخضر ويعدّ ≥18 جدولاً · `ruff` و`mypy` نظيفان ·
تشغيل `/api/v1/analysis` على رمز حقيقي يعيد `NO_TRADE` بسبب `ENGINE_UNAVAILABLE` **ولا يعيد منطقة مختلَقة أبداً**.

---

#### ✅ نتائج تنفيذ M0 (مُنفَّذة ومدفوعة)

**ثغرة أمنية حقيقية اكتُشفت وأُصلحت في أول تشغيل للحارس:** جدول `watchlist_items` لم يكن عليه أي
سياسة RLS إطلاقاً. جدوله الأب `watchlists` محميّ، لكن الابن بلا أعمدة مستأجر وبلا سياسة — فجلسة
مربوطة بمساحة العمل B كانت تقرأ صفوف مساحة العمل A بالاستعلام المباشر:

```
SET ROLE leovee_app;
SELECT set_config('app.workspace_id', '<workspace B>', false);
SELECT count(*) FROM watchlists;       -- 0  ✅ مُرشَّح
SELECT count(*) FROM watchlist_items;  -- 1  ❌ صفّ مساحة العمل A
```

وربط الصفّ بجدول `symbols` كشف الرموز التي يراقبها المستأجر الآخر. الإصلاح: هجرة
`017_watchlist_items_rls.py` بسياسة `watchlist_items_via_watchlist` تشتقّ النطاق من الأب، على غرار
`agent_traces_via_run`. تحقُّق في الاتجاهين: B صار يقرأ 0، وA ما زال يقرأ صفّه.

**ستة نماذج كانت غائبة عن `Base.metadata`** — لم تُستورد في `app/models/__init__.py`
(`Alert`، `JournalEntry`، `McpSession`، `McpAuditEvent`، `ModelConfig`، `Notification`)، وخمسة منها
مربوطة بمساحة العمل. أي فحص يعتمد على البيانات الوصفية كان أعمى عنها، وAlembic autogenerate كان
سيقرأ المخطط خطأً. سُجِّلت جميعاً.

**تصحيح في الخطة:** كنت قد افترضت أن غياب `WITH CHECK` ثغرة كتابة. **هذا غير صحيح** — تحقّقت
تجريبياً: PostgreSQL يعيد استخدام تعبير `USING` كـ `WITH CHECK` في سياسات `FOR ALL`، فالإدراج عبر
المستأجرين مرفوض فعلاً. الشكل الخطير هو سياسة مقيَّدة بـ `SELECT` وحدها، وهذا ما يفحصه الحارس الآن.

**المحرّكات نزعت أنيابها:** أربعة محرّكات كانت تختلق الأدلة (`zones`، `scenarios`، `structure`،
`liquidity`) صارت تعلن عجزها، والمايسترو يفشل مغلقاً بـ `ENGINE_UNAVAILABLE` مع تسمية المحرّكات
العاجزة. وأُصلح خللان اكتُشفا أثناء ذلك: `persist_engine_outputs` كان يكتب صفّ بنية `NEUTRAL` من
حمولة عاجزة، و`run_decision_engine` كان يرمي `ValueError` من `max()` على قائمة فارغة فيحوّل مدخلاً
ناقصاً إلى خطأ 500.

**سجل حالة المحرّكات** (`app/engines/status.py`) يطبع التقدّم في مخرجات CI:
اليوم **3 منفَّذة** (volatility، risk، decision) و**6 عناصر نائبة**.

**الحالة:** 260 اختباراً ناجحاً، وفشلان سابقان لهذا العمل (`test_pipeline_e2e`،
`test_password_reset_and_metrics_auth`) يتكرّران حرفياً على الأساس النظيف.

**بقية M0 — مُنجَزة:**

- **`OHLCBar` صار يحمل الوقت** وانتقل إلى `app/engines/bar.py`، وتحوّل من `Decimal` إلى `float`.
  كان يُسقط الطابع الزمني تماماً، فلم يكن ممكناً إنتاج مرساة `{ts, price}` لأي تعليق على الشارت
  حتى من حيث المبدأ. الحاجز أمام M2 أُزيل.
- **منصّة المرجع الذهبي** (`app/tests/golden.py`) + `docs/PORTING.md`. المقارن نفسه مُختبَر بـ15
  اختباراً — مقارن يفوته فرق يجعل كل نقل ينجح. أدقّها: `bool` نوع فرعي من `int` في بايثون، فبلا
  فحص مرتَّب قبل الفرع العددي كان `broken: True` سيطابق `1` بصمت.
- **ستة ADR** في `docs/adr/` + **بانر تعديلات في رأس `LEOVEE_SPEC.md`** يعلن أن جدول التعديلات
  يسبق أي قسم أدناه، و§0 موسومة `SUPERSEDED` في مكانها. واختبار مطابقة يمنع الفهرس والملفات
  والبانر من التباعد.
- **سقالة i18n** بالعربية افتراضاً وRTL أساساً، مع مفاتيح مطبوعة (استدعاء مفتاح غير معرَّف = خطأ
  بناء)، واتجاه على `documentElement` لا على غلاف حتى يصحّ تخطيط المحتوى المنقول (portals).

**حالة M0: مكتملة.** 293 اختباراً في الخلفية و15 في الواجهة، والفشلان في الخلفية وواحد في الواجهة
سابقة جميعها لهذا العمل ومتكرّرة على الأساس النظيف.

---

#### ✅ أثر D10 — الذهب فقط

جاء القرار أثناء بناء كون الرموز في M1، وهو توقيت مثالي: بدل نقل عشرين أداة، أصبح رمزاً واحداً.
والمكاسب الهندسية حقيقية لا مجرد تقليص:

- **التفاوتات الخاصة بكل أداة تنهار إلى ثوابت.** مقارنة القمم المتساوية في محرك السيولة، وفحص
  السبريد، وحاجز الوقف، وعرض المناطق — كلها تعتمد على حجم النقطة. بأداة واحدة يصير حجم النقطة
  واحداً (`0.01` — الذهب يُسعَّر بمنزلتين، لا `0.0001` كأزواج العملات) بدل جدول يجب أن يصحّ لكل صف.
- **نموذج الجلسة صار نموذج الذهب** لا حالة استثنائية داخل نموذج عام. توقّف الذهب اليومي
  ‏[17:00, 18:00) بتوقيت نيويورك هو ما أنتج خلل «الفجوات الوهمية» في AiChart؛ هنا صار هو التقويم نفسه.
- **الذاكرة صارت قابلة للمقارنة مباشرة.** لم يعد استرجاع الحالات المشابهة يسأل إن كان نظير EURUSD
  يعني شيئاً للذهب — كل حلقة سابقة هي نفس السوق. وهذا يشحذ استرجاع الحالات وإحصاءات الاستراتيجيات
  ومعايرة الثقة، **ويقصّر مشكلة البداية الباردة** (D7) لأن كل نتيجة تصبّ في العيّنة نفسها.
- سلسلة شموع واحدة، واشتراك بثّ واحد، وذاكرة تخزين مؤقت واحدة.

**التطبيق:** `app/core/symbols.py` يحمل قائمة السماح و`require_instrument` **يرمي** بدل أن يستبدل
الذهب صامتاً — الإجابة عن الذهب لمن سأل عن EURUSD تنتج تحليلاً واثقاً لسوق خاطئ، وهذا أسوأ من خطأ.
والهجرة `018_seed_gold_symbol` تزرع الذهب بالبيانات الصحيحة وتحذف ما عداه.

---

### M1 — العمود الفقري لبيانات السوق

**الهدف:** مدخل شموع حتمي ومحدود ومقيَّد بقائمة سماح. كل اختبار محرّك لاحق يعتمد على تجميد هذا.

| من AiChart | إلى Leovee |
|------------|------------|
| `src/lib/markets/forexInstruments.ts` (‏20 رمزاً، `TRADABLE_SYMBOLS`) | `backend/app/core/symbols.py` + هجرة بذور إلى جدول `symbols` |
| `markets/{symbolCatalogue,symbolMapping,symbolCase}.ts` | `app/services/market/symbol_resolver.py` |
| `markets/{tradingCalendar,forex24h}.ts` | `app/services/market/calendar.py` |
| `markets/intervals.ts`، `ohlc/{chartTime,klineLimits}.ts` | `app/services/market/timeframes.py` |
| `ohlc/candleGaps.ts` | يُدمج في `app/services/market/gaps.py` القائم |
| `ohlc/fetchOhlc.ts` (**نقطة الاختناق الوحيدة لقائمة السماح**) | `app/services/market_data.py` — دالة واحدة، والسماح يُفرض فيها وحدها |

**جديد:** سياسة كفاية الشموع (`MIN_GEOMETRY_CANDLES = 60`، `GEOMETRY_WINDOW_BARS = 500` من
`detectGeometry.ts`) كشرط مشترك يفشل مغلقاً بدل تحليل 12 شمعة.

**مخاطر:** جدول `candles` مقسَّم LIST حسب الإطار الزمني — إضافة أطر تحتاج DDL تقسيم في Alembic مع بقاء
`test_alembic_up_down.py` أخضر في الاتجاهين. حدود الجلسات والتوقيت الصيفي مصدر انحراف صامت كلاسيكي.

**معايير الخروج:** طلب رمز خارج العشرين يعيد 4xx من **كل** مسار يقبل رمزاً (اختبار مُعامَل على جدول
الراوترات) · اختبار ذهبي لاختيار نافذة الشموع وتصنيف الفجوات على 20 رمزاً × 4 أطر · اختبار حالة الجلسة
يغطي إغلاق الجمعة وافتتاح الأحد وانتقالَي التوقيت الصيفي.

---

### M2 — البدائيات الحتمية

**الهدف:** أول نقل TS→Python. صغير ونقيّ وأقصى رافعة اختبارية — **يتحقق من صحة المنهج** قبل المخاطرة
بمحرّك الهندسة عليه.

| من | إلى `backend/app/engines/primitives/` |
|----|----|
| `src/lib/ohlc/indicators.ts`، `src/lib/indicators.ts` | `indicators.py` |
| `chart/geometry/pivots.ts` (`zigzagPivots`، `geometryAtr`، `allConfirmedPivots`) | `pivots.py` |
| `ohlc/structure.ts` (الأرجحات، BOS/CHoCH) | `structure.py` |
| `ohlc/marketRegime.ts` | `regime.py` |
| `spread.ts`، `strategies/sessionSpread.ts` | `spread.py` |

**معايير الخروج:** 100% من العيّنات المستخرجة تمرّ عند التفاوت المعلَن، **صفر عيّنة متخطّاة أو موسَّعة
التفاوت** · `mypy strict` بلا `Any` في الحزمة · عدد العيّنات مطبوع في مخرجات CI ليكون انكماشه مرئياً.

---

### M3 — محرك الهندسة

**الهدف:** نقل `src/lib/chart/geometry/` (‏2,604 سطر) — نقيّ ومستقل عن الوكيل وقابل للاختبار بالكامل.
أعلى قيمة وأقل مخاطرة في المشروع، ويغذّي أربعة أسطح: أدلة القرار، رسم الشارت، سرد الأنماط، وسياق MCP.

`types.ts` → نماذج Pydantic (لا قواميس)، ثم `trendlines`، `channels`، `triangles`، `headShoulders`،
`doubleExtremes`، `tripleExtremes`، `flags`، `cupHandle`، `rectangles`، `candlesticks`، `patternStage`،
`patternState`، `detectGeometry` بالأسماء نفسها. ‏`toDrawings.ts` يُؤجَّل إلى M9 (جسر الرسم الدلالي).

**يُحفظ حرفياً — عقد الحدود من `detectGeometry.ts`:** آخر 500 شمعة، ≤2 خط اتجاه لكل جهة، ≤1 قناة،
≤3 أنماط، جميعها فوق ثقة 60، وإزالة تداخل عند >60% من امتداد المراسي الأقصر. الإخراج المحدود هو ما
يجعل اللقطة صالحة كسياق للنموذج؛ إرخاؤه يفجّر ميزانية الرموز وكثافة الرسم معاً.

**يُحفظ حرفياً — الفصل بين `status` (‏forming/completed/invalidated) و`stage`.** محوران مختلفان، وتعليق
AiChart نفسه ينصّ على ذلك؛ دمجهما يفقد حالة «قارب الاكتمال دون تأكيد» التي يستدل بها المُقرِّر.

**مخاطر:** `PatternTypeName` (19 قيمة) و`SemanticDrawingType` (25 قيمة) تصير enums بايثونية يجب أن
تطابق قيمها النصية مفردات الواجهة. وحّد المفردات هنا في مكان واحد، وإلا أعدت التسمية عبر ثلاث طبقات في M9.

**معايير الخروج:** تفاضل ذهبي كامل: النوع والمرحلة والحالة وترتيب مراسي الفهارس و`breakDirection`
و`broken` و`confidence` **تطابق تام**؛ الأسعار المشتقّة ضمن `1e-9` · إعادة إنتاج ملفات اختبار AiChart
الثلاثة كـ pytest (اختبارات **نيّة**، تُحفظ إلى جانب العيّنات) · اختبار حتمية: نفس الشموع ⇐ لقطة مطابقة
بتّياً، 100 تشغيل · اختبار حدود: لا لقطة تتجاوز السقوف الموثَّقة.

---

### M4 — المحرّكات التحليلية + عقد القرار المطبوع

**الهدف:** حذف الـ656 سطراً النائبة. هنا يبدأ المنتج أن يكون حقيقياً.

**جديد أولاً (حاجز):** `backend/app/schemas/engines.py` و`schemas/decision.py` — نماذج Pydantic لكل
مخرَج محرّك ولعقد القرار. **يُجمَّد قبل** إعادة كتابة المحرّكات؛ فهو الواجهة التي ترتبط بها مراحل LLM
(M6) ودورة حياة التوصية (M7) والشارت (M9). ويبدأ حلّ مشكلة «25 راوتراً يعيدون `dict[str, Any]` مقابل
4 ملفات مخططات».

| من (الشقّ الحتمي) | إلى (يستبدل النائب) |
|----|----|
| `agents/structureAgent.ts` + `ohlc/structure.ts` | `engines/structure.py` |
| `agents/liquidityAgent.ts` | `engines/liquidity.py` |
| `agents/supplyDemandAgent.ts` | `engines/zones.py` |
| `ohlc/marketRegime.ts` + ATR | `engines/volatility.py` |
| `agents/multiTimeframeAgent.ts` | `engines/mtf.py` |
| `rewardRisk.ts`، `strategies/{riskPolicy,thresholds}.ts` | `engines/risk.py` |
| `strategies/liveCostProfile.ts` + حساب `executionGuardAgent.ts` | `engines/plan_sanity.py` (**اسم جديد**) |
| `marketContext.ts` + تسجيل الأخبار من `newsMacroAgent.ts` | `engines/market_intelligence.py` |
| تفريع السيناريوهات من `finalDecisionSynthesizer.ts` | `engines/scenario.py` — **سيناريوهان اتجاهيان + سيناريو إبطال** (D6) |

**مخاطر:** وكلاء AiChart المتخصصون يخلطون الحساب الحتمي ببناء المطالبة. افصلهما بحدّة: الشقّ الحتمي
يهبط هنا كمحرّك نقيّ، وشقّ المطالبة ينتظر M6. **لا تدع `provider.complete()` يتسلّل إلى
`backend/app/engines/`** — أضف اختبار مطابقة يؤكد أن `app/engines/**` لا يستورد شيئاً من `app/providers/llm`.

**معايير الخروج:** صفر محرّك يعيد `unavailable` لمدخل سليم من 500 شمعة على العشرين رمزاً · كل مخرَج
يتحقق من مخططه · `mypy strict` لا يرى `dict[str, Any]` يعبر حدّ محرّك · `test_engine_persistence.py`
أخضر بالأشكال الجديدة ويكتب مناطق حقيقية · تحليل من طرف إلى طرف ينتج قراراً غير متدهور بأدلة حقيقية.

---

### M5 — بنية LLM: سجل المطالبات، المهارات، حلقة الأدوات، تضمينات حقيقية *(بالتوازي مع M2–M4)*

**الهدف:** بناء الأربعة التي يفتقدها Leovee كلياً. يعتمد على M0 وحده.

**جديد:**
- `backend/app/prompts/` — سجل مطالبات مُخزَّن في نظام الملفات، مُجزَّأ بالمحتوى، مُصدَّر.
  `prompts/system/constitution.md` و`prompts/stages/*.md` و`prompts/skills/<name>/SKILL.md`، مع تحميل
  كسول للمهارات على غرار `src/lib/agent/skills/`.
- جدول `prompt_versions` (عالمي، في قائمة السماح) + `agent_runs.prompt_hash`. **غير اختياري**: حلقة
  التعلّم في M8 تنسب النتائج إلى القرارات؛ بلا معرفة أي مطالبة أنتجت القرار، المعايرة تقيس ضجيجاً.
- `backend/app/agents/tools/` — سجل + موزّع + حلقة استدعاء الأدوات التي لا مستهلك لها اليوم
  (`LLMToolCall` معرَّف بلا موزّع). **مصدر حقيقة واحد لحلقة العملية ولخادم MCP معاً** (M11).
- `backend/app/providers/llm/embeddings.py` — تضمينات حقيقية خلف `ModelRouter` القائم، تستبدل
  `services/memory/embedding.py` (اليوم SHA-256 باسم `deterministic-v1`). يبقى الحتمي **بديل اختبار**
  في `app/tests/doubles/` لا افتراضاً وقت التشغيل. + مهمة إعادة ملء `memory_embeddings` وعمود وسم نموذج
  حتى لا تُقارَن متجهات `deterministic-v1` بالحقيقية في بحث HNSW واحد.
- `backend/app/agents/context/` ← نقل `src/lib/agent/context/` (13 ملفاً: الضغط، تسجيل الصلة، إصلاح
  أزواج الأدوات، ميزانية الرموز). شرط قبل M6 وإلا فجّر المُقرِّر نافذة السياق.

**الدستور (D8 — يُكتب من الصفر):** يُصاغ `prompts/system/constitution.md` من `LEOVEE_SPEC` مباشرة،
بهوية Leovee، ولا يُنسخ نصّ AiChart. لكنه **يجب أن يستوعب** عقد D6 الثلاثي (الرأي / نوع الخطة / حالة
التنفيذ) وقاعدة «لا تدّعِ دعماً إحصائياً لا تملكه» و«الأدلة تقوّي أو تُضعف ولا تنقض» — هذه صياغات
اشتراها المنتج بالتجربة، ويُعاد التعبير عنها بكلمات Leovee لا بنسخها.

**المهارات:** `pattern-atlas` (213 سطراً) و`trading-lexicon` (88) تُعاد كتابتهما مع **مطابقة أسمائهما
لـ enum الأنماط في M3** — الأطلس والمحرّك مفردة واحدة. ‏`cards` (107) تُعاد كتابتها لسطح React في
Leovee، لكن **تصنيفها للبطاقات هو مواصفة مكوّنات M9/M10**. تسقط بنود التنفيذ وأوضاع التداول والوسطاء.

**عقد الأدوات:** يُشتق من `agent/tools/contract.json` (75 مدخلاً) بعد ترشيح كل ما هو
`riskClass: execution` وكل `place_*`/`close_*`/`modify_*` وكل ما ينفّذه MetaAPI وكل ما يخصّ الباكتيست.
المتوقع بقاء ~40 أداة قراءة/تحليل.

**مخاطر:** الموجّه يدير أصلاً الاحتياط وحدّ الطلبات وميزانية الرموز؛ حلقة الأدوات يجب أن تحترم
**الميزانية نفسها** وإلا استنزفت حلقة جامحة الميزانية في منتصف التحليل. اربط تكرارات الحلقة بمحاسبة
الميزانية القائمة، وضع سقفاً صلباً للتكرارات.

**معايير الخروج:** السجل يحمّل كل الملفات ويكشف تجزئات مستقرة، واختبار يؤكد خلوّ كل ملف مطالبة من
المفردات الممنوعة · الحلقة تنفّذ محادثة أدوات متعددة الأدوار على مزوّد بديل، مع إصلاح أزواج الأدوات على
بثّ مبتور · اختبار التضمين: سلسلتان متقاربتان دلالياً لهما جيب تمام أعلى من غير المرتبطتين (**يفشل**
بالـ SHA-256 — وهذا المقصود).

---

### M6 — خط أنابيب الوكيل: الأسطول المتخصص والمُقرِّر

**الهدف:** استبدال `"You are a trading analyst."` بالشيء الحقيقي. وكيل واحد مرئي فوق أسطول، بنفس رسم
مراحل AiChart المُثبَت.

- `orchestrator.ts::runUnifiedChartAgent` (‏103KB) → `backend/app/agents/orchestrator.py`، بحفظ الرسم:
  `market_data` → (`structure` ∥ `liquidity` ∥ `supply_demand` ∥ `multi_timeframe`) → `news` → `risk`
  → `final_decision` → `drawing`. **`execution_guard` يُحذف**، ويأخذ `plan_sanity` (M4) موضعه كبوابة حتمية.
- `agents/finalDecisionSynthesizer.ts` (‏68KB) → `backend/app/agents/synthesizer.py`؛ مخطط zod →
  Pydantic، و`SynthesizerOutcome`/`SynthesizerFailure`/`SynthesizerFailureKind` تنتقل 1:1.
- شقّ المطالبة لكل متخصص → `backend/app/agents/stages/*.py` + `prompts/stages/*.md`.
- `errorTaxonomy.ts` (مفردات المراحل والأعطال) → `backend/app/agents/error_taxonomy.py`.

**يُحفظ:** المُهَل لكل مرحلة و**سجل المُهَل الصامتة** — قيمة فارغة بلا استثناء مرمي لا يمكن أن تعني إلا
مهلة صامتة، ويجب تسجيلها. دقيقة، مكتسبة بصعوبة، وسهلة الضياع في الترجمة. تُحفظ أعطال المراحل في
`agent_traces` القائم.

**يُحفظ:** عقد fail-closed في Leovee **أقوى** من الوضع المتدهور في AiChart. أبقِ عقد Leovee. رسائل
AiChart التشغيلية للتدهور تنتقل كـ**تفسير** للـ `NO_TRADE`، لا كمسار حوله.

**مخاطر:** أعلى تعقيد في المشروع — 171KB من TS في ملفّين. خفّفها بنقل **رسم المراحل وتصنيف الأعطال
أولاً** بمراحل صورية تعيد مخرجات معلَّبة، تخضيرها، ثم ملء مرحلة واحدة في كل مرة، كل واحدة في PR مستقل
خلف راية تفعيل افتراضها fail-closed.

**معايير الخروج:** توسيع `test_orchestrator_llm_unavailable.py`: كل مرحلة تُجبَر على الفشل/المهلة
استقلالاً ⇐ `NO_TRADE` بالمرحلة الصحيحة في `agent_traces` (12 حالة مُعامَلة) · تزامن المراحل المتوازية
مُثبَت بقياس زمن الجدار مقابل بديل مُبطَّأ · تكامل كامل على نافذة شموع ذهبية بمزوّد مكتوب ينتج قراراً
مستقرّاً ومطابقاً للمخطط · ميزانية الرموز محترمة في أسوأ عيّنة · صفر `dict[str, Any]` في حزمة الوكيل.

---

### M7 — دورة حياة التوصية الأساسية

**الهدف:** نقل نظام التوصيات (‏17,283 سطراً): آلة الحالة، المراجعات، التفعيل، إعادة التقييم، القابلية
للتداول، النتائج — **مربوطاً بمساحة العمل**.

| من `src/lib/recommendations/` | إلى `backend/app/services/recommendations/` |
|----|----|
| `canonical/{types,stateMachine}.ts` | توسعة `models/recommendation.py` + `state_machine.py` |
| `canonical/repository.ts` (630) | `repository.py` — **معامل `userId` يُحذف**، والـ RLS هو المرشِّح الوحيد |
| `canonical/revisions.ts` (542) | `revisions.py` + جدول `recommendation_revisions` |
| `canonical/{outcomes,evidenceSnapshots,replay,tradeLessons,analytics}.ts` | الوحدات المقابلة |
| `canonical/planContract.ts` | `schemas/plan.py` |
| `activationRule.ts` (25KB) | `activation.py` |
| `reevaluationCycle.ts` (29KB)، `reevaluationTriggers.ts` | `reevaluation.py` + جدولة arq |
| `recommendationTracker.ts` (22KB) | `tracker.py` + مهمة arq |
| `tradability.ts`، `tradabilityCalibration.ts` | `tradability.py` (‏now/soon/watch_only) |
| `performanceJournal.ts`، `recommendationStats.ts` | تُدمج في `performance_service.py` و`journal_service.py` |

**قاعدة العزل الحاكمة (تمنع نقل صنف الخطأ):** لا دالة في `services/recommendations/` تقبل
`user_id`/`workspace_id`/`tenant_id` كمرشِّح نطاق. ‏`canonical/repository.ts` يمرّر `userId` عبر 630
سطراً من المرشِّحات اليدوية؛ نقل هذا التوقيع ينقل صنف الخطأ. في Leovee يجب أن تكون الدالة **عاجزة عن
التعبير** عن استعلام عابر للمستأجرين.

**توفيق مفردات الحالة:** AiChart فيه 10 حالات، وLeovee أقل. نتبنّى مفردات AiChart (الأنضج) عبر هجرة
enum، **ناقص** الحالات التنفيذية (`partially_closed`) إلا إن أُبقيت للخروج الجزئي المسجَّل يدوياً.
قرار صريح مكتوب، لا افتراض.

**مخاطر:** `revisions.ts` يشفّر الفرق بين الحالة التي **أعلنتها** المراجعة و`executionState` الحيّة على
الصف — وتعليق `canonical/types.ts` ينصّ صراحةً أن شارة البطاقة تقرأ الصف لا المراجعة. فقدان ذلك ينتج
شارات بائتة في الواجهة. يُختبَر مباشرةً.

**معايير الخروج:** جدول انتقالات آلة الحالة مختبَر: كل انتقال شرعي يمرّ وكل غير شرعي يُرفض · اختبار
مساحتَي عمل على كل جدول جديد (تلقائي عبر M0) · تدقيق توقيعات المستودع · اختبار المراجعة مقابل الحالة الحيّة.

---

### M8 — حلقة التعلّم: ذاكرة الحالات، إحصاءات الاستراتيجيات، DNA

**الهدف:** إغلاق حلقة التغذية الراجعة نتيجة ← معايرة ← قرار. هذا ما يجعل التوصيات **تزداد دقة** — وهو
مخرَج المشروع المطلوب.

| من | إلى |
|----|----|
| `src/lib/marketMemory/` (‏1,936 سطراً: `caseFingerprint`، `caseVector`، `caseIndexer`، `caseQuery`، `forwardOutcome`، `liveCases`) | `backend/app/services/memory/cases/` — المتجهات تهبط في `memory_embeddings` القائم (‏`Vector(1536)` + HNSW)، وقد صارت حقيقية بعد M5 |
| `src/lib/strategies/` **بعد إسقاط كل ما هو باكتيست** (‏`catalog`، `matchingKeys`، `selectionBias`، `calibration`، `decayLifecycle`، `supportSummary`، `thresholds`) | `backend/app/services/strategies/` — الكتالوج عالمي، والإحصاءات لكل مساحة عمل في `strategy_stats` القائم |
| `src/lib/tradingDna/` بلا `backtestEvidence`/`shadowTrader` | `backend/app/services/trading_dna/` — مربوط بالكامل بمساحة العمل |
| `semanticMemory.ts`، `memoryLifecycle.ts`، `userProfileMemory.ts` | تُدمج في `services/memory/` و`services/learning/decay.py` القائمين |

**تكامل مع القائم:** `services/learning/{pipeline,outcome_recorder,statistics,calibration,decay,memory_writer,terminal_hooks}.py`
وجداول `lessons`/`calibration_bins`/`outcome_records` موجودة بتنفيذ رقيق — هذه المرحلة **تملؤها ولا
تكرّرها**. دقّق التداخل قبل الكتابة.

**أثر D7 هنا:** بلا باكتيست، مصدر الدعم الإحصائي الوحيد هو النتائج الحقيقية. لذا:
- كل استراتيجية تبدأ **بلا سابقة** — لا يجوز تسليم مساحة عمل جديدة معايرةً واثقة من بيانات غيرها.
- **سياسة البداية الباردة** صريحة ومختبَرة: فترات ثقة واسعة، وقابلية `watch_only`، والتوصية تُنشر
  موسومةً «تحليل مباشر بلا دعم إحصائي» حتى بلوغ N عيّنة.

**معايير الخروج:** اختبار استرجاع ذهبي: نافذة تاريخية مبصومة تسترجع نظائرها المعروفة · اختبار معايرة:
تيار نتائج اصطناعي يحرّك `calibration_bins` في الاتجاه الصحيح والثقة المعروضة تتبع معدّل الإصابة
المحقَّق · **اختبار تسرّب عبر مساحات العمل**: معايرة B غير متأثرة بنتائج A · اختبار البداية الباردة.

---

### M9 — طبقة الشارت: TradingView مُضمَّنة + النموذج الدلالي

**الهدف:** تنفيذ D9. **هذه أرخص مرحلة مما بدت** لأن المحوّلات صارت قابلة للنقل TS→TS.

**العقد (قائم بالفعل — يُوسَّع لا يُستبدل):**
```
مخرجات المحرّكات (M3/M4)
  → chart_semantic.py  (Python)
  → ChartSemanticModel  (backend/app/schemas/chart.py)
  → HTTP / SSE
  → SemanticAnnotation  (frontend/src/chart/ChartTypes.ts)   ← يبقى كما هو
  → ChartAnnotationRenderer.ts  (محايد عن العارض)
  → TradingViewAdapter.ts  (الملف الوحيد الذي يعرف المكتبة)
```

**خلفية:**
- `chart/geometry/toDrawings.ts` (269) → `backend/app/engines/geometry/to_annotations.py`
- `src/lib/chartDrawings.ts` — الأنواع الـ25 والأدوار الـ18 وأسماء الأنماط الـ19 →
  `backend/app/schemas/chart.py`، **يستبدل `ChartSemanticType` الحالي ذا القيم الست**
- `agents/drawingAgent.ts` → `backend/app/agents/stages/drawing.py`
- `Mt5NativeDrawingType` (27 قيمة) **لا يُنقل** — MT5 خارج النطاق

**واجهة:**
- **تضمين المكتبة**: `frontend/vendor/tradingview/charting_library/` (تعريفات الأنواع) +
  `frontend/public/charting_library/` (وقت التشغيل)، ملتزَمَين عبر **Git LFS**. يُحذف
  `scripts/provision-tradingview.mjs` ومتغيّرا البيئة. حارس CI يفشل إن صارت رؤية المستودع عامة.
- **نقل TS→TS**: `chart/tv/{tvDatafeed,tvDrawingAdapter,tvStudyAdapter,tvUserDrawings,spreadPriceLines}.ts`
  و`components/chart/TvChart.tsx` → `frontend/src/chart/tradingview/`. التحويلات: إزالة `"use client"`،
  `next/dynamic` → `React.lazy`، تعديل مسارات الاستيراد، واستبدال مصدر البيانات بـ TanStack Query +
  عميل Leovee.
- `TradingViewAdapter.ts` ينفّذ واجهة `ChartEngine` القائمة — فلا يتغيّر شيء فوقها.
- **يُحذف**: تبعية `klinecharts`، و`frontend/src/chart/{KLineChartAdapter,ChartDataAdapter}.ts`.
- `ChartAnnotationRenderer.ts` (اليوم 108 أسطر) يكتسب **مقارنة فرقية**: إضافة/تحديث/حذف حسب
  `id` و`version` بدل مسح وإعادة رسم — وإلا ارتجف الشارت مع كل إعادة تقييم حيّة من M7.

**سياسة المؤشرات:** مؤشرات المكتبة **للعرض فقط**. كل ما يستدل به الوكيل يأتي من مؤشرات Python (M2) عبر
الـ API. لا تدع العميل يعيد اشتقاق رقم يعتمد عليه القرار — هكذا يختلف الشارت والسرد بصمت.

**معايير الخروج:** كل نوع دلالي يُرسَم (vitest على بديل للمكتبة) · اختبار ذهاب وإياب: لقطة هندسية →
تعليقات → تسلسل → عكس التسلسل → مطابقة · اختبار المقارنة الفرقية: تغيير تعليق واحد يُصدر تحديثاً واحداً
لا إعادة رسم كاملة · حارس نصّي: `klinecharts` لا يظهر في `frontend/src/`، واستيراد TradingView يظهر في
`TradingViewAdapter.ts` وحده · البناء مكتفٍ ذاتياً بلا شبكة خاصة.

---

### M10 — العربية وRTL ونظام التصميم

**الهدف:** واجهة Leovee اليوم بلا i18n وبلا RTL وبلا مكتبة مكوّنات، ونصوصها إنجليزية مثبّتة في الكود.
العربية الافتراضية مع RTL أساسياً وقاموس مختبَر التكافؤ ونظام تصميم مفروض بالاختبارات — أصل منتج حقيقي
في AiChart. سقالة M0 جعلت المكوّنات الجديدة تولد مترجَمة؛ هذه المرحلة هي النشر والتحديث الرجعي.

| من | إلى |
|----|----|
| `src/lib/i18n/{ar,en,types,index}.ts` (~830 سطراً لكلٍّ، ~727 مفتاحاً) | `frontend/src/i18n/` — مُرشَّحة من مفاتيح التنفيذ/تليجرام/MT5/الباكتيست، وموسَّعة لأسطح Leovee |
| اختبار تكافؤ المفاتيح | vitest |
| `DESIGN.md` | `frontend/DESIGN.md` + `frontend/src/styles/tokens.css` |
| تصنيف البطاقات في `skills/cards/SKILL.md` | `frontend/src/components/cards/` |

**غير قابل للتفاوض (منقول من نظام AiChart):** العربية هي الافتراضية · ألوان الشراء/البيع تعني **اتجاه
صفقة فقط** ولا تُستخدم أبداً كنجاح/خطأ عام · شارات القابلية: `now`→ألوان الشراء، `soon`→تحذير،
`watch_only`→مكتوم، و`rejected` **لا يُرسم كبطاقة أبداً** · لا أزرار إجراءات سريعة ساكنة في المحادثة
(مفروض باختبار) · الخصائص المنطقية فقط (`ms-`/`me-`/`start-`/`end-`) بقاعدة lint تمنع `ml-`/`mr-`/`left-`/`right-`.

**مخاطر:** ~70 حالة vitest قائمة تؤكد على نصوص إنجليزية. حوّلها لتؤكد على **مفاتيح الترجمة** أو
`data-testid`، لا على النص المعروض — وإلا كسر كل تعديل نسخة الاختبارات مستقبلاً.

**معايير الخروج:** تكافؤ مفاتيح `ar`/`en` تام · لا نصّ مواجه للمستخدم مثبَّت في `frontend/src/` (قاعدة
lint) · صفر صنف اتجاه فيزيائي · توسيع مواصفة Playwright: تدفق كامل بالعربية RTL · اختبار تباين AA على
رموز الشراء/البيع/التحذير في الوضعين.

---

### M11 — تكافؤ MCP والمراقبة والتحوّل النهائي

**MCP:** Leovee فيه 4 أدوات من ~25. خادم AiChart Node بـ68 أداة **لا يُنقل كـ runtime** — تُنقل
**تعريفات** الأدوات. سجل M5 هو مصدر الحقيقة، وM11 يكشفه عبر نقل MCP HTTP باستخدام `bind_workspace_rls`.
سجل واحد، نقلان، نموذج صلاحيات واحد. المستهدف ~40 أداة قراءة/تحليل؛ كل أداة تنفيذ تبقى محذوفة.

**المراقبة:** استبدال العدّادات في الذاكرة (`app/observability/http_metrics.py`) بـ `prometheus_client`،
وإضافة عدّادات زمن/فشل لكل مرحلة وكيل مفتاحها تصنيف الأعطال من M5، وتوقيتات المحرّكات، وتكرارات حلقة
الأدوات، ورموز/كلفة LLM. مع حفظ حماية `/metrics` القائمة.

**التحوّل:**
- مصفوفة تكافؤ: كل سطح في AiChart ← مقابله في Leovee، أو **«لم يُنقل، والسبب…»** صريحاً.
- **تشغيل ظلّي**: نفس الرمز ونفس النافذة على النظامين، ومقارنة القرارين. كل اختلاف إما خطأ مُفسَّر أو
  تحسين مُفسَّر — لا شيء بلا تفسير.
- أرشفة مرجع AiChart إلى وسم للقراءة فقط.

**معايير الخروج:** عدد أدوات MCP يطابق العقد المرشَّح، ولكل أداة اختبار تكامل واختبار مربوط بالـ RLS ·
`/metrics` بصيغة Prometheus حقيقية · CI كامل أخضر · تقرير التشغيل الظلّي موقَّع ·
`test_no_execution_surface.py` أخضر طوال الطريق.

---

## 7. الملفات الحرجة

| الملف | الدور |
|-------|-------|
| `backend/alembic/versions/005_learning_rls_candles.py` | نمط `RLS_WORKSPACE_TABLES` + `_workspace_rls_policy()` — كل جدول مُرحَّل ينضم إليه |
| `backend/app/agents/orchestrator.py` | رسم المراحل وعقد fail-closed — يُعاد كتابته في M6، ويُمسّ في M0/M4 |
| `backend/app/engines/zones.py` | أسوأ نائب (يختلق مناطق بقوة `0.5`) — ممثّل الاثني عشر جميعاً |
| `backend/app/engines/volatility.py::OHLCBar` | `Decimal`→`float` + إضافة `ts`/`volume` — حاجز M2 |
| `backend/app/services/analysis_service.py` | شكل خط الأنابيب الموصول فعلاً — نقطة تكامل M4/M6/M7/M8 |
| `frontend/src/chart/ChartTypes.ts` | عقد `ChartEngine` المحايد — ما يجعل استبدال العارض رخيصاً |
| `/workspace/aichart/src/lib/chart/geometry/detectGeometry.ts` | عقد الحدود (500 شمعة، ≤2 خط/جهة، ≤1 قناة، ≤3 أنماط، ثقة ≥60، إزالة تداخل >60%) — يجب أن ينجو من M3 سليماً |
| `/workspace/aichart/src/lib/agent/agents/finalDecisionSynthesizer.ts` | العقل المُقرِّر (68KB) — أثقل نقل مفرد، M6 |
| `/workspace/aichart/src/lib/recommendations/canonical/repository.ts` | 630 سطراً من مرشِّحات `userId` اليدوية — **المكان الذي يُنقل منه صنف خطأ العزل إن لم ننتبه** |

---

## 8. التحقق (Verification)

**في كل مرحلة، قبل الدمج:**
```bash
cd backend && ruff check app && ruff format --check app && mypy app && pytest app/tests -q
cd frontend && npm run lint && npm run typecheck && npm run test && npm run build
```

**بوابات دائمة تعمل من M0 إلى النهاية:**
```bash
pytest backend/app/tests/conformance/          # تغطية RLS + عزل مساحتَي عمل + غياب سطح التنفيذ
pytest backend/app/tests/golden/ -v            # التفاضل مقابل المرجع الذهبي (يطبع عدد العيّنات)
pytest backend/app/tests/test_rls_isolation.py backend/app/tests/test_multi_tenant_security_s100.py
pytest backend/app/tests/test_alembic_up_down.py
```

**تحقق من طرف إلى طرف على المكدّس الحقيقي:**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
docker compose run --rm migrate
# صحّة الخدمة
curl -s localhost:8000/health/ready
# تحليل حقيقي — يجب أن يعيد اتجاهاً (D6) أو NO_TRADE بسبب تشغيلي مُسمّى، ولا شيء بينهما
curl -s -X POST localhost:8000/api/v1/analysis/run \
  -H "Authorization: Bearer $TOKEN" -H "X-Workspace-Id: $WS" \
  -d '{"symbol":"EURUSD","timeframe":"1H","complete_pipeline":true}'
# التعليقات الدلالية للشارت
curl -s "localhost:8000/api/v1/chart/annotations?symbol=EURUSD" -H "X-Workspace-Id: $WS"
```
ثم في المتصفح على `localhost:3000`: تسجيل الدخول ← `/analyst` ← EURUSD ← تشغيل تحليل ← التحقق بصرياً
من أن المناطق وخطوط الاتجاه والأنماط المرسومة **تطابق** مخرجات `/chart/annotations` رقمياً، وأن السرد
يستشهد بنفس المستويات.

**بوابة القبول النهائية (M11):** تشغيل ظلّي على 20 رمزاً × 3 أطر: قرار AiChart مقابل قرار Leovee،
وتقرير يصنّف كل اختلاف إمّا «خطأ نقل» أو «تحسين مقصود». لا خانة ثالثة.

---

## 9. المخاطر الرئيسية

| الخطر | التخفيف |
|-------|---------|
| **انحراف رقمي صامت** في النقل الحتمي | المرجع الذهبي + سياسة تفاوت `1e-9` + `numeric.py` للمصائد الأربعة. أي تفاوت أوسع = خطأ نقل يُصلَح، لا يُقبَل |
| **نقل صنف خطأ العزل** من `repository.ts` | قاعدة صارمة: لا دالة مستودع تقبل معامل نطاق. + اختبار مطابقة مولَّد يغطي كل جدول جديد تلقائياً |
| **ضخامة M6** (‏171KB في ملفّين) | رسم المراحل أولاً بمراحل صورية، ثم مرحلة واحدة لكل PR خلف راية افتراضها fail-closed |
| **تسرّب LLM إلى طبقة المحرّكات** | اختبار مطابقة: `app/engines/**` لا يستورد `app/providers/llm` |
| **حلقة أدوات جامحة** تستنزف ميزانية الرموز | ربط التكرارات بمحاسبة `ModelRouter` القائمة + سقف صلب |
| **ترخيص TradingView وحجم المستودع** | Git LFS + حارس CI على رؤية المستودع + تعديل `LEOVEE_SPEC §43` و`ARCHITECTURE.md` |
| **البداية الباردة للمعايرة** بعد إلغاء الباكتيست | سياسة مكتوبة ومختبَرة: فترات واسعة، `watch_only`، ووسم «بلا دعم إحصائي» حتى N عيّنة |
| **تقسيم `candles` حسب الإطار الزمني** يكسر الهجرات | DDL تقسيم في Alembic مع بقاء `test_alembic_up_down.py` أخضر في الاتجاهين |
| **اختبارات الواجهة المربوطة بالنصّ الإنجليزي** | تحويلها إلى مفاتيح ترجمة/`data-testid` في M10 |

---

## 10. انحرافات موثَّقة عن `LEOVEE_SPEC.md` (تستوجب تعديل الوثيقة)

| البند | المواصفة تقول | القرار |
|-------|----------------|--------|
| §0 | «مشروع greenfield، لا نظام قديم، لا تنتج خطط ترحيل» | **مُلغى** — هذا المستند هو خطة الترحيل |
| §43/§44 | KLineChart هو العارض الأساسي الإلزامي | **TradingView Advanced Charts** مُضمَّنة داخل المستودع (D9) |
| §64 | الباكتيست وإعادة العرض | **الباكتيست والتحقق الإحصائي مُلغيان** (D7)؛ تبقى إعادة العرض كمراجعة بصرية |
| §110 خطوة 17 | توليد سيناريو «لا صفقة» | **سيناريوهان اتجاهيان + سيناريو إبطال** (D6) |
| §19 / §57 | سلامة التنفيذ وقسم الصفقات | **لا تنفيذ**؛ قسم الصفقات يصير سجلاً يدوياً يغذّي التعلّم (D4) |
| §105 | الإشعارات | **مُلغاة** عدا بريد التحقق/استعادة كلمة المرور (D5) |
| §17 | OANDA + ربط حساب المستخدم | بيانات OANDA تبقى؛ **ربط حساب الوسيط مُلغى** (D3) |
| §82 | الواجهة بلا ذكر i18n | **العربية افتراضية وRTL أساسي** (M10) |

**إجراء مطلوب في M0:** تحديث `LEOVEE_SPEC.md` و`ARCHITECTURE.md` و`IMPLEMENTATION_PLAN.md` بهذه
الانحرافات، وإضافة ADR لكل واحد. إبقاء الوثيقة تناقض الكود هو بالضبط ما أنتج فجوة المحرّكات الفارغة.
