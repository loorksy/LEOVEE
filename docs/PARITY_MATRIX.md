# مصفوفة التكافؤ — AiChart (Lonora) ← Leovee

بند الخروج في M11: **كل سطح في AiChart إمّا له مقابل مُسمّى في Leovee، أو «لم يُنقل» بسبب مكتوب.
لا خانة ثالثة.** هذه الوثيقة هي ذلك السجل، وتُقرأ مع
[`AICHART_MIGRATION_PLAN.md`](AICHART_MIGRATION_PLAN.md) وقرارات المالك D1–D13 وسجلّات
[`docs/adr/`](adr/).

الرموز: ✅ مُرحَّل (أُعيدت كتابته داخل معمارية Leovee) · 🔁 مُرحَّل بتغيير مقصود موثَّق ·
⛔ لم يُنقل عمداً — والسبب في الصف نفسه.

---

## 1. المحرّكات الحتمية

| سطح AiChart | Leovee | الحالة |
|---|---|---|
| `chart/geometry/` (2,604 سطراً: trendlines، channels، triangles، H&S، double/triple، flags، cup&handle، rectangles، candlesticks، patternStage/State، detectGeometry) | `backend/app/engines/geometry/` | ✅ تفاضل ذهبي كامل؛ عقد الحدود (500 شمعة، ≤2 خط/جهة، ≤1 قناة، ≤3 أنماط، ثقة ≥60، إزالة تداخل >60%) منقول حرفياً ومُختبَر |
| `ohlc/indicators.ts`، `indicators.ts` | `engines/primitives/indicators.py` | ✅ ذهبي |
| `chart/geometry/pivots.ts` (zigzag، geometryAtr) | `engines/primitives/pivots.py` | ✅ ذهبي |
| `ohlc/structure.ts` + الشقّ الحتمي من `structureAgent.ts` | `engines/primitives/structure.py` + `engines/structure.py` | ✅ |
| `ohlc/marketRegime.ts` | `engines/primitives/regime.py` + `engines/volatility.py` | 🔁 فرع `volatile` كان ميتاً في المرجع (recentAtr من نفس نافذة atr — النسبة 1.0 دوماً)؛ أُحيي بقياس خط أساس يستثني النافذة المحكومة، والجانبان مُثبَّتان باختبار. الانحراف موثَّق في الكود |
| `agents/liquidityAgent.ts` (الشقّ الحتمي) | `engines/liquidity.py` | ✅ |
| `agents/supplyDemandAgent.ts` (الشقّ الحتمي) | `engines/zones.py` | ✅ يستبدل العنصر النائب الذي كان يختلق منطقتين بقوة 0.5 |
| `agents/multiTimeframeAgent.ts` | `engines/mtf.py` | 🔁 السلّم صار `H4/H1/M15` بدل `D1/H4/H1` (D11) |
| `rewardRisk.ts`، `strategies/riskPolicy.ts` | `engines/risk.py` | 🔁 الحجم من مسافة الوقف وحدها؛ لا مُدخل سبريد (D12) |
| `strategies/liveCostProfile.ts` + حساب `executionGuardAgent.ts` | `engines/plan_sanity.py` | 🔁 **نموذج الكلفة حُذف بكامله** (D12): أرضية الضجيج = وسيط الظلّ المقاس من الشموع، أرضية الهدف = نصف ATR، والسبريد الملحوظ يُبلَّغ ولا يبوّب أبداً |
| `spread.ts`، `strategies/sessionSpread.ts` | — | ⛔ D12: لا شيء يُنمذَج من السبريد. البديل قياسي من السعر الحيّ في `plan_sanity.py` |
| تفريع السيناريوهات من `finalDecisionSynthesizer.ts` | `engines/scenario.py` | 🔁 سيناريوهان اتجاهيان + سيناريو **إبطال**؛ لا سيناريو امتناع (D6) |
| `agents/executionGuardAgent.ts` كمرحلة تنفيذ | — | ⛔ D4: لا تنفيذ. حسابه التحليلي وحده انتقل إلى `plan_sanity.py` أعلاه |

## 2. خط أنابيب الوكيل وبنية LLM

| سطح AiChart | Leovee | الحالة |
|---|---|---|
| `orchestrator.ts::runUnifiedChartAgent` (103KB) | `app/agents/orchestrator.py` | ✅ رسم المراحل محفوظ؛ `execution_guard` حُذف و`plan_sanity` بوابة حتمية مكانه؛ عقد fail-closed الأقوى في Leovee هو الساري |
| `agents/finalDecisionSynthesizer.ts` (68KB) | `app/agents/synthesizer.py` | ✅ zod ← Pydantic؛ `SynthesizerOutcome/Failure/FailureKind` بنفس الدلالة |
| `errorTaxonomy.ts` | `app/agents/error_taxonomy.py` | ✅ وهو مفتاح وسوم مقاييس المراحل في Prometheus |
| مطالبات المتخصصين | `app/agents/stages/` + `app/prompts/stages/` | ✅ سجل مطالبات مُجزَّأ بالمحتوى مع `prompt_versions` و`agent_runs.prompt_hash` |
| `SYSTEM.md` (الدستور) | `app/prompts/system/constitution.md` | 🔁 D8: كُتب من الصفر بهوية Leovee؛ يستوعب عقد D6 الثلاثي و«لا تدّعِ دعماً إحصائياً لا تملكه» |
| `agent/context/` (13 ملفاً: ضغط، صلة، إصلاح أزواج الأدوات، ميزانية) | `app/agents/context/` | ✅ |
| `agent/skills/{pattern-atlas,trading-lexicon,cards}` | `app/prompts/skills/` | 🔁 أسماء الأطلس مطابقة لـ enum أنماط M3؛ بنود التنفيذ والوسطاء سقطت |
| اختيار الإطار الزمني | `app/agents/timeframe.py` | 🔁 جديد شكلاً، مطلوب بـ D11: الوكيل يختار M1/M5/M15 بقياس مقروئية البنية؛ `INSUFFICIENT_BARS`/`NO_READABLE_STRUCTURE` وحدهما يستبعدان |
| التضمينات | `app/providers/llm/embeddings.py` | ✅ حقيقية خلف `ModelRouter`؛ بديل SHA-256 بقي **بديل اختبار** فقط |

## 3. دورة حياة التوصية

| سطح AiChart | Leovee | الحالة |
|---|---|---|
| `recommendations/canonical/{types,stateMachine}.ts` | `models/recommendation.py` + `services/recommendations/state_machine.py` | ✅ جدول الانتقالات مُختبَر في الاتجاهين |
| `canonical/repository.ts` (630 سطراً من مرشِّحات `userId` اليدوية) | `services/recommendations/repository.py` | 🔁 **صنف الخطأ لم يُنقل**: لا دالة تقبل مُعامل نطاق؛ RLS هو المرشِّح الوحيد، واختبار مطابقة مولَّد يفرض ذلك على كل جدول |
| `canonical/revisions.ts` | `revisions.py` | ✅ التمييز بين حالة المراجعة المعلنة و`executionState` الحيّ محفوظ ومُختبَر |
| `activationRule.ts` | `activation.py` | ✅ |
| `reevaluationCycle.ts` + `reevaluationTriggers.ts` | `reevaluation.py` + جدولة arq | 🔁 عتبات مقيسة لا منقولة: COOLDOWN=15د، ≤6 دورات آلية، إعادة القياس عند تضاعف الضجيج |
| `recommendationTracker.ts` | `tracker.py` + مهمة arq | ✅ |
| `tradability.ts` | `tradability.py` | 🔁 `now/soon/watch_only` محفوظة؛ **بلا سقف بداية باردة يفرض `watch_only`** — السجل الفارغ لا يحجب توصية أبداً؛ الوسم الإلزامي «تحليل مباشر بلا دعم إحصائي» هو البديل (قرار مالك) |
| `canonical/{outcomes,evidenceSnapshots,tradeLessons}.ts` | `services/learning/outcome_recorder.py` وما حوله | 🔁 سلامة النتائج بمفتاح فريد في القاعدة (`dedupe_key`) لا بحارس اقرأ-ثم-قرّر |
| `performanceJournal.ts`، `recommendationStats.ts` | `performance_service.py`، `journal_service.py` | ✅ |
| `canonical/replay.ts` | `services/replay/` | 🔁 D7: أداة مراجعة **بصرية** فقط؛ ليست تحققاً إحصائياً |

## 4. حلقة التعلّم

| سطح AiChart | Leovee | الحالة |
|---|---|---|
| `marketMemory/` (caseFingerprint، caseVector، caseIndexer، caseQuery، forwardOutcome) | `services/memory/cases/` + جدول `market_cases` | 🔁 ذهبي على البصمة والنتيجة؛ الحالات **عالمية للمنصّة** (حقائق سوق) بقرار موثَّق — لا تُجمع أبداً مع `strategy_stats` المعزولة بالـ RLS |
| `strategies/` بعد إسقاط الباكتيست (matchingKeys، calibration، supportSummary، decayLifecycle، thresholds) | `services/strategies/` | ✅ المعايرة (Wilson + bootstrap) مُثبَّتة بمرجع ذهبي؛ `UNKNOWN≠ANY` في مفاتيح المطابقة |
| `strategies/{backtestCapital,catalogGen}.ts` وأدلة الباكتيست في `evidence.ts` | — | ⛔ D7: النتائج الحقيقية للتوصيات المغلقة هي الدليل الإحصائي الوحيد |
| `tradingDna/` بلا `backtestEvidence`/`shadowTrader` | `services/trading_dna/` | 🔁 10 مقاييس بقيت، 8 أُسقطت بسبب مكتوب لكلٍّ (مصدرها تنفيذ أو باكتيست)؛ بوابات عيّنة دنيا صريحة |
| `semanticMemory.ts`، `memoryLifecycle.ts` | `services/memory/` + `services/learning/decay.py` | 🔁 نوافذ متدحرجة، ترشيح كل الأعمدة الستة في الدلاء |
| `research-service/` (12,789 سطراً: باكتيست، walk-forward، Monte Carlo، سرب أبحاث) | — | ⛔ D7 بكامله |

## 5. طبقة الشارت

| سطح AiChart | Leovee | الحالة |
|---|---|---|
| `chartDrawings.ts` (24 نوعاً دلالياً + 18 دوراً + 19 اسم نمط) | `backend/app/schemas/chart.py` + `frontend/src/chart/ChartTypes.ts` | ✅ مفردة واحدة عبر الطبقات الثلاث؛ النوع (ماذا) والدور (لماذا) محوران متعامدان |
| `chart/geometry/toDrawings.ts` | `backend/app/engines/geometry/to_annotations.py` | ✅ forming=متقطّع؛ تخليق lead-in/exit لـ H&S؛ مراسي `{ts, price}` حقيقية |
| `chart/tv/{tvDatafeed,tvDrawingAdapter,…}.ts` + `TvChart.tsx` | `frontend/src/chart/tradingview/` | ✅ نقل TS←TS (‏Next←Vite)؛ زمن الشمعة ميلي‌ثانية وزمن الشكل ثوانٍ — موثَّق في الكود |
| مكتبة TradingView نفسها | `frontend/vendor/tradingview/` + `frontend/public/charting_library/` | 🔁 **الكود جاهز والثنائيات محجوبة بميزانية Git LFS للحساب** — انظر `frontend/vendor/tradingview/README.md` و`BLOCKED_ON_OWNER.md`؛ حارس الترخيص `scripts/check_repo_visibility.sh` قائم |
| KLineChart (`KLineChartAdapter`، `ChartDataAdapter`، تبعية `klinecharts`) | — | ⛔ D9؛ حارس نصّي يمنع عودتها |
| `Mt5NativeDrawingType` (27 قيمة) | — | ⛔ D3: لا MT5 |

## 6. الواجهة: العربية والتصميم

| سطح AiChart | Leovee | الحالة |
|---|---|---|
| `lib/i18n/{ar,en,types,index}.ts` (~727 مفتاحاً) | `frontend/src/i18n/` (252 مفتاحاً) | 🔁 مُرشَّحة من مفردات التنفيذ/MT5/الباكتيست/الإشعارات؛ العربية مصدرًا وRTL أساسًا؛ **الطبقة مفتوحة لعدد اللغات**: قاموس جديد + سطر في `LOCALES` يكفيان، ومبدّل اللغة select لا toggle |
| نظام التصميم (`DESIGN.md`) | `frontend/DESIGN.md` + `src/styles/tokens.css` + `src/designRules.test.ts` | ✅ ألوان الشراء/البيع اتجاه صفقة فقط؛ خصائص منطقية فقط؛ لا أزرار إجراءات سريعة في المحادثة — كلها قواعد مفروضة باختبار لا بالذاكرة |
| اختبارات الواجهة المربوطة بالنص الإنجليزي | — | 🔁 حُوِّلت جميعها إلى `data-testid` وبيانات خام؛ تغيير نصّ لم يعد يكسر اختباراً |

## 7. أدوات MCP

خادم AiChart المستقل (Node/Express، 68 أداة) **لم يُنقل كـ runtime** — سجل الأدوات في
`backend/app/agents/tools/` هو مصدر الحقيقة الوحيد، ويُكشف عبر ناقلَين: حلقة أدوات الوكيل،
ونقل MCP HTTP في `backend/app/mcp/` تحت `bind_workspace_rls`. سجل واحد، نقلان، نموذج صلاحيات
واحد — الأداة لا يمكن أن تتصرف بشكل مختلف حسب الباب الذي دخلت منه.

| صنف أدوات AiChart | المصير | السبب |
|---|---|---|
| القراءة والتحليل (شموع، مؤشرات، بنية، هندسة، سيولة، مناطق، ذاكرة، توصيات، إحصاءات) | ✅ أُعيد بناؤها في السجل الموحّد (**TOOL_COUNT_MARKER أداة**؛ العدّ يُفرض باختبار مطابقة بأرضية دنيا) | — |
| كل `place_*`/`close_*`/`modify_*` وكل ما ينفّذه MetaAPI | ⛔ | D3/D4 |
| أدوات MT5 (‏20 مسار `api/agent/mt/*`) | ⛔ | D3 |
| أدوات الباكتيست | ⛔ | D7 |
| أدوات الإشعارات | ⛔ | D5 |
| أدوات رموز متعددة | 🔁 انهارت إلى الذهب وحده؛ `require_instrument` يرمي ولا يستبدل | D10 |

خصائص السجل المفروضة ميكانيكياً (`test_tool_registry_conformance.py`): كل أداة تعلن نطاقها
(`platform`/`workspace`)؛ لا مُعامل `workspace_id`/`tenant_id`/`user_id` في أي مخطط أداة؛
الأسماء القديمة المنقوطة (`market.get_candles` وأخواتها) أسماء بديلة تُحلّ إلى أدوات السجل.

## 8. المراقبة

| سطح AiChart | Leovee | الحالة |
|---|---|---|
| عدّادات في الذاكرة | `app/observability/prometheus.py` (`prometheus_client`) | ✅ زمن/فشل لكل مرحلة بمفاتيح تصنيف الأعطال، توقيتات المحرّكات، تكرارات حلقة الأدوات، رموز/كلفة LLM، تطبيع المسارات ضد انفجار الكاردينالية؛ حماية `/metrics` محفوظة |

## 9. ما استُبعد جملةً (لا مقابل ولا حاجة لواحد)

| المستبعَد | القرار |
|---|---|
| MetaAPI بكامله، جسور MT5، ربط حساب الوسيط | D3 |
| التنفيذ: `execution.ts`، `executionSafety`، `killSwitch`، `approvalFlow`، `autoExecutor`، `tradeManagement` | D4 — `models/trade.py` في Leovee **سجل يدوي** يغذّي التعلّم، ومسار التنفيذ غير موجود أصلاً (`test_no_execution_surface.py` يفرض ذلك نصياً على الشجرة كلها) |
| تلجرام كقناة إشعار، Web Push، ملخّصات البريد | D5 — تلجرام بقي **قناة محادثة فقط** يبدؤها المستخدم (D13، ADR 0009) |
| `research-service/` والتحقق الإحصائي | D7 |
| `db/{sqlite,pg,sql}.ts` (~200KB طبقة بيانات يدوية) | معمارية Leovee: SQLAlchemy 2 + Alembic |
| `store.ts` (50KB / 90 تصديراً) | فُكِّك إلى خدمات؛ الكائن الإلهي لا يُنقل |
| المصادقة والفوترة والأدمن في AiChart | نسخ Leovee أقوى (RLS + RBAC + argon2) وبقيت |
| سكربتات عابرة، مسارات `web/` القديمة، مرجع اختبار ميت | مخلّفات |

## 10. التشغيل الظلّي — الوضع الصادق

بوابة M11 الأصلية («نفس الرمز والنافذة على النظامين») صيغت قبل D10/D11 وقبل أن يتقرر أن مرجع
AiChart **شجرة قراءة فقط**: تشغيله الحيّ يتطلب Node + قواعد بياناته + مزوّديه ببيانات اعتماد
حقيقية، وهذا غير متاح ولا مرغوب في بيئة الترحيل. البديل المكافئ الذي نُفِّذ فعلاً وأقوى برهاناً
على الشقّ الحتمي:

- **التفاضل الذهبي الملتزَم**: مخرجات المرجع الحقيقية (تُولَّد بتشغيل TypeScript المرجعي نفسه عبر
  Node مرة واحدة) ملتزَمة في `backend/app/tests/fixtures/golden/` وتُقارن عند كل تشغيل اختبار
  بسياسة `1e-9` — أي فرق أوسع خطأ نقل يُصلَح لا يُقبَل.
- كل فرق مقصود موثَّق **في مكانه** في الكود والاختبار (أمثلة: إحياء فرع `volatile` الميت، حذف
  نموذج السبريد، سلّم MTF الجديد) — لا شيء بلا تفسير، وهو نصّ البوابة الأصلي.
- الشقّ الاحتمالي (المُقرِّر LLM) لا مرجع ذهبياً له بطبيعته، ويُختبَر بسيناريوهات مرجعية
  (سوق ← القرار المسموح) كما في المرجع نفسه.

## 11. أرشفة المرجع

وسم القراءة فقط على مستودع `loorksy/AiChart` **إجراء مالك** (نطاق النشر هنا مقصور على
`loorksy/leovee`). المطلوب: وسم `pre-leovee-migration-reference` على آخر commit في فرعه
الافتراضي، ثم أرشفة المستودع من إعدادات GitHub. مُدرج في `BLOCKED_ON_OWNER.md`.
