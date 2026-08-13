PROJECT SPECIFICATION — LEOVEE

Production-Grade Multi-Tenant AI Forex Trading SaaS
Python + FastAPI + React + TypeScript + OANDA + MCP Apps + KLineChart

AI Trading Agent:
Research → Market Intelligence → Multi-Timeframe Analysis
→ Scenario Generation → Adversarial Validation → Risk
→ Recommendation → Human-Like Chart Drawing → Monitoring
→ Memory → Learning

SaaS:
Multi-User → Workspace Isolation → Authentication
→ Billing → Usage → Permissions → Admin → Audit → Observability

============================================================
AMENDMENTS — READ BEFORE ANY SECTION BELOW
============================================================

This specification was written as a greenfield brief. It is no longer accurate
in ten places, and the sections below have NOT been rewritten — the amendments
are listed here instead so the original intent stays readable alongside what was
actually decided. Where this table and a section disagree, THIS TABLE WINS.

Full reasoning: docs/adr/ (one record per decision) and
docs/AICHART_MIGRATION_PLAN.md.

| Section | The spec says | Actual decision | ADR |
|---------|---------------|-----------------|-----|
| §0 | Greenfield; no legacy system; produce no migration plan | SUPERSEDED. loorksy/AiChart implements this product and is the reference implementation being ported from. Leovee's architecture is final. | 0001 |
| §110 step 17 | Generate a "no-trade" scenario alongside bullish and bearish | Two directional scenarios plus an INVALIDATION scenario. A successful analysis always carries a direction; NO_TRADE is reserved for operational failure with a named cause. | 0002 |
| §64 | Backtesting and replay | Backtesting and statistical validation are OUT OF SCOPE. Chart replay survives as a visual review tool only. | 0003 |
| §43, §44 | KLineChart is mandatory and must not be replaced | TradingView Advanced Charts, vendored in-repo under Git LFS rather than fetched at build time. | 0004 |
| §19, §57 | Execution safety; trades section | No execution of any kind. The trades section becomes a manual journal of user-reported fills, feeding outcome learning. | 0005 |
| §105 | Notifications | No external notifications. Transactional email (verification, password reset) only. | 0005 |
| §17, §18 | OANDA data plus user account connection | OANDA market data stays. Broker account linking is out of scope. | 0005 |
| §17, §60 | A multi-instrument Forex platform with a watchlist | The tradable universe is XAUUSD alone. Everything else is rejected at the data layer. | 0007 |
| §82 | Frontend architecture, no i18n mentioned | Arabic is the default locale and RTL is the primary direction. | — |
| §3 | Pydantic/SQLAlchemy stack, no numeric policy | Deterministic engines compute in float to match the JavaScript reference; Decimal is confined to the money boundary. | 0006 |

A note on why this banner exists rather than an edited spec. §0 instructed the
build to treat the product as having no prior implementation. The engine layer
was therefore written against prose instead of ported from working code, and
shipped as placeholders — some of which fabricated evidence and presented it to
users as measurement. A specification that contradicts the code is not a
harmless inconsistency; that contradiction is what produced the gap.

============================================================
0. PROJECT IDENTITY
============================================================

Product name: Leovee

Use "Leovee" consistently in: branding, UI, package names, repository naming, documentation, emails, and the MCP server name (leovee-mcp).

SUPERSEDED (see AMENDMENTS above, ADR 0001). This was written as a greenfield brief; in fact loorksy/AiChart implements this product and is the reference implementation the domain logic is ported from. Leovee's architecture — FastAPI, SQLAlchemy, Postgres with row-level security, React/Vite — is final and is not replaced by AiChart's.

Original text, kept for the record: "This is a GREENFIELD project. There is NO existing repository, NO existing code, and NO legacy system to migrate. Do not search for existing code. Do not produce migration plans."

This is a FULL PRODUCTION build — not an MVP, not a prototype, not a proof of concept. Every feature described in this specification is in scope. Nothing may be stubbed, mocked, or left as "TODO for later" unless this specification explicitly marks it optional. Quality bar: production-grade, tested, secure, observable.

The build is phased (see IMPLEMENTATION PHASES), but every phase must be completed to production quality before the project is considered done.

============================================================
1. ROLE
============================================================

You are a senior: AI systems architect, quantitative trading engineer, Python backend engineer, React/TypeScript frontend engineer, SaaS architect, multi-tenant systems engineer, AI agent engineer, MCP engineer, security engineer, DevOps engineer.

Your task is to design and implement Leovee: a production-grade, multi-tenant AI Forex Trading SaaS.

The product is an AI market analyst. It is NOT merely "AI → BUY / SELL". The system must behave like an intelligent trading research and analysis workspace.

The AI must:
1. Observe the market.
2. Collect and validate market data.
3. Understand market structure.
4. Analyze multiple timeframes.
5. Detect liquidity.
6. Detect supply/demand and important price zones.
7. Analyze volatility.
8. Research relevant news and fundamentals.
9. Generate multiple market scenarios.
10. Challenge its own scenarios.
11. Calculate risk deterministically.
12. Produce structured recommendations.
13. Explain the recommendation using evidence.
14. Draw the analysis on the chart.
15. Monitor the thesis continuously.
16. Update or invalidate the thesis when conditions change.
17. Remember every analysis, recommendation, thesis, and outcome (long-term memory).
18. Learn from outcomes: calibrate confidence, track strategy performance, distill lessons.
19. Maintain conversation and analytical memory per workspace.
20. Support multiple users and isolated workspaces.
21. Provide an MCP server and MCP App-compatible experiences.
22. Provide a complete admin control plane.

The system must never pretend certainty.

============================================================
2. GREENFIELD RULE — DESIGN BEFORE CODING
============================================================

DO NOT WRITE APPLICATION CODE FIRST.

Because this is greenfield, there is no audit step. Instead, start by producing the complete design documentation set:

1. ARCHITECTURE.md
2. DATABASE_SCHEMA.md
3. AGENT_ARCHITECTURE.md
4. MEMORY_ARCHITECTURE.md
5. MCP_ARCHITECTURE.md
6. SAAS_ARCHITECTURE.md
7. DEPLOYMENT.md
8. IMPLEMENTATION_PLAN.md

Each document must be complete and internally consistent with this specification. Only after these documents exist should implementation begin, following the phases in this specification.

============================================================
3. TECHNOLOGY STACK
============================================================

BACKEND:
Python 3.12+, FastAPI.
Use: Pydantic v2, SQLAlchemy 2.x, Alembic, asyncpg, httpx, WebSockets, asyncio, structlog, pytest, mypy, ruff.

AI SDKs:
Anthropic official Python SDK (anthropic) and OpenAI official Python SDK (openai).
Both providers must be abstracted behind a unified internal LLM provider interface. Do NOT tightly couple business logic to either provider.

FRONTEND:
React, TypeScript, Vite.
Use: React Router, TanStack Query, Zustand where appropriate, Tailwind CSS, a component system, WebSocket client, charting abstraction, KLineChart.

CHARTING:
KLineChart MUST be the primary charting library for the trading chart experience.
Pin a single KLineChart major version (v9.x line) in package.json at project setup, document the exact version in ARCHITECTURE.md, and do not mix API styles from different major versions. Any future major-version upgrade is a dedicated, tested task.

KLineChart is the canonical frontend chart renderer for: candlestick charts, OHLC visualization, technical indicators, price/time coordinate rendering, overlays, analysis visualization, interactive navigation, zoom, pan, crosshair, timeframe switching, real-time candle updates, annotations, and AI-generated analysis drawings.

Do NOT replace KLineChart with another charting library for the primary trading chart.
Keep KLineChart behind an internal chart abstraction so business logic never depends directly on KLineChart APIs.
The backend and AI agents must NEVER directly manipulate KLineChart. The AI produces semantic chart instructions; the frontend chart renderer converts them into KLineChart-compatible operations.

DATABASE:
PostgreSQL, with the pgvector extension enabled (required by the memory system).

CACHE:
Redis.

BACKGROUND JOBS:
Prefer Arq or Celery. Choose one and document the decision in ARCHITECTURE.md.

REAL-TIME:
WebSocket.

MESSAGE / EVENT SYSTEM:
Redis Streams or an equivalent event abstraction.

MARKET DATA:
OANDA v20 as the primary Forex market-data provider — BOTH interfaces:
- REST API for instruments, historical candles, and account operations.
- Streaming API (pricing stream) for real-time prices; live candles are aggregated server-side from the stream. Do not build real-time on REST polling; polling is only the documented fallback when the stream disconnects.
Handle OANDA rate limits explicitly: connection limits on streams, request throttling on REST, exponential backoff with jitter on errors, and stream reconnection with gap backfill (fetch missed candles via REST after reconnect).
The provider must be abstracted so additional providers can be added later.

NEWS / ECONOMIC CALENDAR DATA:
Define a NewsProvider and EconomicCalendarProvider interface with pluggable adapters. Implement at least one concrete production adapter for each (e.g. Finnhub, Financial Modeling Prep, or Trading Economics — choose based on API access and document the decision). LLM web search may be used only as a supplementary research source, always with source provenance, never as the primary calendar/news feed.

EMAIL:
Define an EmailProvider abstraction with a concrete production adapter (e.g. Resend, AWS SES, or SMTP — choose and document). Used for verification, password reset, alerts, and notifications.

PAYMENTS:
Define a PaymentProvider abstraction with adapters. Implement a concrete Stripe adapter plus a manual-invoice/offline adapter. **Current default is `BILLING_PROVIDER=manual`** (code / staging); switch to Stripe when production Stripe credentials are supplied. Entitlement logic must not depend on any single processor.

MCP:
Build a dedicated MCP server (leovee-mcp) compatible with https://github.com/modelcontextprotocol/ext-apps. Use the official MCP Apps architecture where appropriate.

TIMEZONES / SESSIONS:
All timestamps stored in UTC. Trading session detection (Sydney, Tokyo, London, New York) must use IANA timezone definitions with correct DST handling — never fixed UTC offsets. Session boundaries must be configurable and unit-tested across DST transitions.

============================================================
4. PRODUCT VISION
============================================================

Leovee should feel like: "An AI trading analyst workspace that learns" — not "an automated trading bot."

Core experience:
USER → WORKSPACE → AI CHAT → MARKET CONTEXT → AI ANALYSIS → KLINECHART → TRADE SETUP → THESIS → MONITORING → OUTCOME → MEMORY → LEARNING

============================================================
5. MULTI-TENANT SAAS ARCHITECTURE
============================================================

This is a true multi-user SaaS. Every user must have an isolated workspace.

Architecture:
Platform → Organization/Tenant → Workspace → User → Conversations → Analyses → Watchlists → Recommendations → Theses → Trades → Memories

Use logical multi-tenancy with strict tenant isolation. Every tenant-owned record must contain tenant_id and, where appropriate, workspace_id. All queries must enforce tenant isolation. Never trust tenant_id supplied by the client — derive it from the authenticated session/token.

============================================================
6. WORKSPACE
============================================================

Each user receives a personal workspace containing: conversations, chat history, saved analyses, watchlists, symbols, recommendations, trade ideas, theses, chart layouts, chart preferences, chart annotations, alerts, preferences, connected OANDA accounts, AI settings, agent memory, usage, subscription, notifications.

Example — Workspace "Ahmed's Trading Workspace":
Symbols: EURUSD, GBPUSD, XAUUSD, USDJPY.
Conversations: "EURUSD London Session", "USDJPY FOMC Analysis", "Gold Setup".

============================================================
7. AUTHENTICATION
============================================================

Production-grade authentication supporting: email/password, secure password hashing (argon2/bcrypt), email verification, password reset, session management, refresh tokens, access tokens, logout, session revocation, optional OAuth architecture, optional MFA architecture.

Never store plaintext passwords. Use secure cookies where appropriate. Implement CSRF protection where applicable. Rate-limit: login, signup, password reset, API authentication.

============================================================
8. AUTHORIZATION
============================================================

Implement RBAC. Roles: SUPER_ADMIN, ADMIN, SUPPORT, ANALYST, USER.

Granular permissions, e.g.: workspace.read, workspace.write, analysis.create, analysis.read, trade.read, trade.create, billing.read, billing.manage, memory.read, memory.manage, admin.users.read, admin.users.manage, admin.system.read, admin.system.manage, admin.ai.manage, admin.providers.manage, admin.audit.read.

============================================================
9. USER EXPERIENCE — MAIN APPLICATION
============================================================

SIDEBAR:
1. Home
2. AI Analyst
3. Chat
4. Markets
5. Watchlist
6. Analysis
7. Trades
8. Recommendations
9. Alerts
10. Journal
11. Research
12. Memory
13. Performance
14. Settings
Plus: Backtesting, Replay, API / MCP, Billing.

============================================================
10. USER HOME DASHBOARD
============================================================

Home shows: market overview, watchlist, active recommendations, active theses, recent AI analyses, recent conversations, market events, upcoming high-impact news, active alerts, performance summary, recent lessons learned by the agent.

============================================================
11. AI CHAT SECTION
============================================================

The Chat section is a central product feature.

UI: Conversation list + Chat interface + Context panel + KLineChart.

Conversation list shows: title, symbol, last message, timestamp, status, unread state.
Users can: create, rename, delete, archive, search, pin, duplicate conversations.

============================================================
12. CHAT MEMORY (CONVERSATION LAYER)
============================================================

Chat history must be persisted. Store: messages, role, content, tool calls, tool results, attachments, symbol context, chart context, analysis references, timestamps, token usage, model/provider, latency.

Do not blindly send the entire chat history to the LLM. Implement context management using: recent messages, summarized history, relevant workspace memory, relevant agent memories (see AGENT MEMORY & LEARNING), relevant market context, relevant thesis, relevant analysis.

============================================================
13. AI CHAT MODES
============================================================

Support: CHAT, ANALYZE, RESEARCH, CHART, TRADE SETUP, EXPLAIN, REVIEW, RECALL.

Examples:
"Analyze EURUSD"
"Why did you invalidate this setup?"
"Show me the liquidity on 15M"
"Research USD fundamentals"
"Draw your analysis on the chart"
"Review my previous EURUSD setup"
"What did you learn from our last 10 gold trades?"
"How does EURUSD usually behave during London open?"

============================================================
14. AI AGENT ARCHITECTURE
============================================================

Layered agent architecture:

Layer 1: Data Layer
Layer 2: Market Intelligence
Layer 3: Technical Analysis
Layer 4: Fundamental / News Intelligence
Layer 5: Research
Layer 6: Reasoning
Layer 7: Scenario Engine
Layer 8: Adversarial Validation
Layer 9: Risk Engine
Layer 10: Decision Engine
Layer 11: Recommendation Engine
Layer 12: Chart Intelligence
Layer 13: Thesis Monitor
Layer 14: Memory & Learning (first-class layer — see dedicated section)
Layer 15: Orchestration

============================================================
15. AGENT LOOP
============================================================

PERCEIVE → RECALL → UNDERSTAND → RESEARCH → HYPOTHESIZE → CHALLENGE → RISK CHECK → DECIDE → VISUALIZE → MONITOR → UPDATE → RECORD OUTCOME → LEARN

RECALL: before reasoning, the agent retrieves relevant memories (symbol behavior profile, similar past setups, strategy statistics, past lessons, user preferences).
LEARN: after every terminal outcome (target reached, invalidated, expired, closed trade), the agent records the outcome, updates statistics, recalibrates confidence, and distills lessons.

The agent must never skip deterministic validation.

============================================================
16. AGENT MEMORY & LEARNING SYSTEM (CORE REQUIREMENT)
============================================================

The agent must remember everything relevant and learn from it. Memory is a first-class subsystem with its own architecture document (MEMORY_ARCHITECTURE.md).

16.1 MEMORY TYPES

EPISODIC MEMORY:
Every agent run, analysis, scenario set, recommendation, thesis, state transition, and final outcome is stored as a retrievable episode with full provenance (symbol, timeframes, market regime, session, volatility state, evidence used, decision, outcome, R achieved).

SEMANTIC MEMORY (SYMBOL KNOWLEDGE):
Distilled, continuously updated knowledge per symbol, e.g.: typical session behavior, level respect rates, average spread by session, breakout vs fake-breakout tendencies, volatility profile, news sensitivity. Each entry carries sample size, confidence, last_updated, and the episodes it was derived from.

STRATEGY / PROCEDURAL MEMORY:
Per-strategy and per-setup-type performance statistics: occurrences, win rate, average R, profit factor, expectancy, performance by regime/session/volatility bucket. Stored per workspace and aggregated per symbol.

LESSON MEMORY:
Structured lessons distilled from outcomes, especially failures. Each lesson: statement, supporting episodes, conditions where it applies, confidence, created_at, decay/aging policy.

WORKSPACE / USER MEMORY:
User preferences, corrections, feedback (accepted/rejected recommendations, thumbs up/down, manual notes), risk preferences, style preferences. Stored separately from market facts.

CONVERSATION MEMORY:
Rolling summaries per conversation (see CHAT MEMORY).

16.2 LEARNING LOOP

For every terminal outcome:
1. Record the outcome deterministically (OutcomeRecorder — no LLM involvement in recording facts).
2. Attribute the outcome to the strategy, regime, session, and evidence used.
3. Update strategy statistics and symbol semantic memory.
4. Recalibrate confidence: maintain calibration bins mapping stated confidence → realized accuracy; future confidence values must be adjusted by calibration data. Confidence shown to users must be calibrated, not raw LLM intuition.
5. Run a MemoryWriter step (LLM-assisted, evidence-grounded) that distills candidate lessons; lessons are stored as structured records referencing their source episodes.
6. Detect strategy decay: compare rolling live performance vs historical expectation; flag or auto-suspend strategies that diverge beyond a configurable threshold.

16.3 RETRIEVAL

Hybrid retrieval injected into agent context at RECALL:
- Structured queries (symbol, timeframe, regime, session, setup type, strategy).
- Vector similarity over episode/lesson embeddings (pgvector).
- Recency and relevance ranking with configurable budgets (token limits per memory category).
Retrieved memories are presented to the LLM as evidence with provenance, clearly labeled as historical memory, never as current market fact.

16.4 MEMORY GUARDRAILS

- Memory is evidence, never a substitute for live data. Live market data always overrides memory.
- Minimum sample sizes before semantic/strategy conclusions are treated as reliable (configurable, e.g. n ≥ 20); below threshold, memories are labeled LOW_SAMPLE.
- Memories age: freshness weighting and decay; stale lessons are down-ranked and eventually archived.
- Regime awareness: statistics are always bucketed by regime/session/volatility to avoid overfitting a single market condition.
- All memory is tenant/workspace scoped. No cross-workspace leakage — ever. Platform-level aggregate learning across tenants is out of scope unless explicitly anonymized, aggregated, and admin-enabled behind a feature flag.
- The LLM can propose memories; only validated structured records are persisted. The LLM never writes raw free-text into memory tables without schema validation.
- Users can view, search, correct, and delete their agent's memories from the Memory section. Deletion cascades to derived statistics recomputation.
- Never store secrets, credentials, or personal identifying information inside market memory.

16.5 MEMORY UI (USER-FACING "MEMORY" SECTION)

Users can browse: symbol knowledge profiles, strategy statistics, lessons learned, calibration accuracy, recent episodes, and manage (edit/delete) memories. The AI must be able to answer "what have you learned about X?" from this store with citations to episodes.

============================================================
17. MARKET DATA — OANDA
============================================================

Implement OandaMarketDataProvider (REST + streaming as defined in the stack section) implementing a MarketDataProvider interface.

Use OANDA v20 for: instruments, candles, pricing (stream + REST), account information where authorized, orders only if execution is explicitly enabled, positions only if execution is explicitly enabled, transactions where appropriate.

Primary analysis data: OHLC, bid, ask, spread, candle completion, timestamps, volume where available, pricing.

Normalize OANDA data into internal models. Never expose OANDA-specific structures throughout the application. Future providers must be addable without rewriting the agent.

CANDLE STORAGE & RETENTION:
- Persist historical candles per symbol/timeframe in PostgreSQL with idempotent upserts (no duplicates, out-of-order safe).
- Retention policy (configurable defaults): 1M ≥ 1 year, 5M/15M/30M ≥ 3 years, 1H/4H/1D full available history.
- Backfill jobs load history on symbol activation; gap-detection jobs repair missing ranges.
- Document expected data volume and indexing strategy (symbol, timeframe, timestamp composite indexes; consider table partitioning by symbol/timeframe).

============================================================
18. OANDA ACCOUNT CONNECTION
============================================================

Users can connect their own OANDA account: demo or live. Store credentials securely: encryption at rest, key management abstraction, secret rotation architecture, masked UI, audit logs. Never store raw API tokens in plaintext. The user must explicitly choose DEMO or LIVE; the UI must clearly distinguish them. Default: DEMO.

============================================================
19. EXECUTION SAFETY
============================================================

Leovee is RECOMMENDATION-FIRST. No automatic trading by default. Separate ANALYSIS from EXECUTION.

If execution is enabled (explicit user opt-in): kill switch, max daily loss, max risk, max position size, max open trades, duplicate order protection, broker validation, execution confirmation, audit trail, emergency shutdown.

============================================================
20. MARKET INTELLIGENCE ENGINE
============================================================

Detect: trend, range, consolidation, expansion, contraction, momentum, exhaustion, breakout, fake breakout, structural highs/lows, support, resistance, liquidity, volatility. Do not depend on one indicator.

============================================================
21. MULTI-TIMEFRAME ENGINE
============================================================

Default — HTF: 1D, 4H. MTF: 1H, 30M, 15M. LTF: 5M, 1M. Configurable.
The engine must establish: HTF bias → MTF structure → LTF setup → Entry trigger.

============================================================
22. MARKET STRUCTURE ENGINE
============================================================

Detect: HH, HL, LH, LL, BOS, CHOCH, MSS, swing highs, swing lows, displacement, breakout, retest, consolidation.
Every event includes: price, timestamp, timeframe, strength, confidence, evidence, invalidation.

============================================================
23. LIQUIDITY ENGINE
============================================================

Detect: equal highs, equal lows, previous day high/low, previous week high/low, session highs/lows, swing liquidity, breakout liquidity, liquidity sweeps.
Distinguish LIQUIDITY TARGET from LIQUIDITY SWEEP. A sweep is evidence, NOT an automatic reversal signal.

============================================================
24. SUPPLY / DEMAND ENGINE
============================================================

Detect: supply, demand, support, resistance, reaction zones, imbalance, FVG-like structures, order-block-like structures.
Each zone: upper, lower, timeframe, created_at, strength, freshness, mitigation, reaction_count, confidence. Zones decay over time.

============================================================
25. VOLATILITY ENGINE
============================================================

Classify: LOW, NORMAL, HIGH, EXTREME.
Use: ATR, ATR percentile, candle range, spread, recent volatility, session. Risk must adapt to volatility.

============================================================
26. NEWS / FUNDAMENTAL ENGINE
============================================================

For every currency pair determine base and quote currency, then research: central banks, interest rates, inflation, employment, GDP, economic events, geopolitical risks, monetary policy, market expectations — via the configured NewsProvider / EconomicCalendarProvider adapters.

Every research item: { source, published_at, headline, summary, relevance, confidence, currency, market_impact }.
Never assume NEWS = BUY/SELL.

============================================================
27. RESEARCH AGENT
============================================================

ResearchAgent responsibilities:
1. Determine missing information.
2. Search targeted information.
3. Compare sources.
4. Detect contradictions.
5. Rank evidence.
6. Return structured research.

Primary question: "What information could invalidate the current thesis?"

============================================================
28. MULTI-HYPOTHESIS ENGINE
============================================================

Always evaluate: Scenario A BULLISH, Scenario B BEARISH, Scenario C NO TRADE. Optional: BREAKOUT, FALSE BREAKOUT.
For each: evidence, contradictions, trigger, invalidation, targets, confidence, risk/reward.

============================================================
29. ADVERSARIAL AGENT
============================================================

DevilsAdvocateAgent — its job: ATTACK THE TRADE. Ask: why could this be wrong?
Check: opposing timeframe, nearby liquidity, news, spread, volatility, weak confirmation, poor R:R, overextension, false breakout — AND relevant lesson memory (has this failure pattern happened before under similar conditions?).
The setup must pass validation.

============================================================
30. REASONING ENGINE
============================================================

The LLM must reason over structured evidence. Never allow the LLM to invent: prices, candle values, indicators, news, SL, TP, support, resistance, or memory statistics.
Deterministic tools provide facts. LLM provides: interpretation, synthesis, scenario comparison, contradiction analysis, explanation.

============================================================
31. ANTHROPIC SDK
============================================================

Integrate the official Anthropic Python SDK. Create AnthropicProvider.
Responsibilities: model invocation, streaming, tool calls, structured outputs, retries, timeouts, usage tracking, error normalization.
Do not expose Anthropic-specific implementation outside the provider layer.

============================================================
32. OPENAI SDK
============================================================

Integrate the official OpenAI Python SDK. Create OpenAIProvider.
Responsibilities: model invocation, Responses API, tool calling, structured outputs, streaming, retries, timeouts, usage tracking, error normalization.

============================================================
33. UNIFIED LLM PROVIDER
============================================================

Create LLMProvider interface: generate(), stream(), tool_call(), structured_output().
Implement AnthropicProvider and OpenAIProvider.
The agent routes workloads, e.g. FAST → OpenAI fast model, REASONING → Anthropic reasoning model, RESEARCH → configurable.
Do not hard-code model names throughout the codebase. Store model configuration centrally.

============================================================
34. MODEL ROUTER
============================================================

ModelRouter responsibilities: select provider, select model, choose based on task, control cost, fallback, retries, rate limits.
Simple extraction → FAST_MODEL. Scenario comparison → REASONING_MODEL. Research synthesis → RESEARCH_MODEL. Emergency fallback → SECONDARY_PROVIDER.

============================================================
35. TOOL SYSTEM
============================================================

Expose controlled tools, e.g.:
get_market_snapshot(), get_ohlc(), get_multi_timeframe_data(), detect_market_structure(), detect_liquidity(), detect_zones(), calculate_volatility(), search_news(), search_economic_calendar(), get_session_context(), calculate_risk(), calculate_position_size(), get_previous_thesis(), validate_thesis(), create_chart_annotation(), get_workspace_context(),
memory.search(), memory.get_symbol_profile(), memory.get_strategy_stats(), memory.get_lessons(), memory.get_similar_episodes(), memory.propose_lesson().

LLM must never access infrastructure directly. Memory write paths are schema-validated; the LLM can only propose, never directly persist.

============================================================
36. RISK ENGINE
============================================================

Risk calculations must be deterministic.
Calculate: stop distance, position size, risk percentage, account risk, reward, R:R, pip value, spread impact, volatility-adjusted stop.
Configurable: risk per trade, daily risk, max positions, correlated exposure, minimum R:R.

============================================================
37. TRADE SETUP ENGINE
============================================================

States: WATCH, SETUP_FORMING, WAITING_CONFIRMATION, READY, ACTIVE, WEAKENING, INVALIDATED, TARGET_REACHED, EXPIRED, NO_TRADE.

============================================================
38. DECISION ENGINE
============================================================

Allowed decisions: BUY, SELL, WAIT, NO_TRADE. Never force a trade.
The decision engine must consult calibrated confidence and strategy statistics from memory; a strategy flagged as decayed or suspended must not produce READY recommendations.

============================================================
39. RECOMMENDATION ENGINE
============================================================

Every recommendation must include: symbol, direction, status, entry, stop, targets, risk/reward, calibrated confidence, thesis, supporting evidence, contradicting evidence, invalidation, research, relevant memory citations, chart annotations, data quality, timestamp.

============================================================
40. THESIS SYSTEM
============================================================

Every serious recommendation creates a Thesis, e.g.:
"EURUSD bullish while price remains above X and 15M structure remains bullish."
States: ACTIVE, STRENGTHENING, WEAKENING, INVALIDATED, TARGET_REACHED, EXPIRED.
Every terminal thesis state triggers the LEARN step (outcome recording, statistics update, lesson distillation).

============================================================
41. THESIS MONITOR
============================================================

Monitor: price, structure, volatility, spread, news, timeframe alignment, liquidity.
When the thesis changes, update the recommendation (e.g. ACTIVE → WEAKENING → INVALIDATED). The system must explain why.

============================================================
42. CHART INTELLIGENCE
============================================================

Create ChartSemanticModel. The AI does not draw pixels; it creates semantic instructions, e.g.:
DRAW_ZONE { type: demand, timeframe: 1H, importance: HIGH, reason: HTF demand }
DRAW_STRUCTURE { type: bullish_BOS, timeframe: 15M }
DRAW_LIQUIDITY { type: equal_lows }
DRAW_SETUP { type: long, entry_zone: [...], stop: [...], targets: [...] }

ChartSemanticModel MUST remain renderer-agnostic — no KLineChart-specific details. The frontend chart layer translates semantic operations into KLineChart drawing operations.

============================================================
43. KLINECHART INTEGRATION
============================================================

KLineChart MUST be the primary chart rendering engine, behind a dedicated frontend abstraction.

Structure (adaptable):
frontend/src/chart/
  KLineChartAdapter.ts
  ChartController.ts
  ChartDataAdapter.ts
  ChartAnnotationRenderer.ts
  ChartIndicatorManager.ts
  ChartInteractionManager.ts
  ChartTimeframeManager.ts
  ChartTypes.ts

Create an internal ChartEngine abstraction; the rest of the frontend communicates with ChartEngine, not KLineChart directly. The KLineChart adapter implements ChartEngine.

Responsibilities: initialize/destroy chart, update/append candles, update latest candle, change symbol, change timeframe, zoom, pan, crosshair, resize, synchronize viewport, render/remove/update annotations, render indicators, manage chart state, expose user interactions, synchronize real-time market data, synchronize AI-generated chart instructions.

Do not put trading/business logic inside the KLineChart adapter. KLineChart is a renderer, not a trading decision engine.

============================================================
44. KLINECHART DATA MODEL
============================================================

Normalize backend/OANDA candle data before sending it to KLineChart. Internal normalized candle model:
Candle: timestamp, open, high, low, close, volume, complete.

Correctly handle: historical candle loading, incremental updates, partial/current candle updates, completed candle updates, missing candles, duplicate candles, out-of-order updates, timeframe changes, symbol changes.

============================================================
45. HUMAN-LIKE CHART DRAWING
============================================================

The chart should resemble a professional analyst's chart.
Avoid: clutter, excessive labels, drawing every candle, unnecessary indicators, perfectly repetitive shapes.
Use: selective annotations, natural line lengths, meaningful labels, contextual positioning, visual hierarchy.
The AI must decide what NOT to draw. KLineChart only renders annotations approved by the chart semantic layer.

Semantic elements to support: horizontal levels, price zones, trend lines, structure markers, liquidity markers, entry zones, stop-loss levels, take-profit levels, invalidation levels, target levels, breakout markers, sweep markers, FVG/imbalance regions, support/resistance, supply/demand, annotations and labels.

============================================================
46. CHART GEOMETRY
============================================================

Never store chart drawings as screen pixels. Store timestamp + price. The renderer converts TIME + PRICE into SCREEN X + SCREEN Y, so drawings remain correct during zoom, pan, resize, and timeframe changes. The backend must remain independent of chart viewport dimensions. Annotations anchor to market coordinates, not screen coordinates.

============================================================
47. CHART STATE MANAGEMENT
============================================================

Chart state includes: symbol, timeframe, visible range, candle data, active annotations, selected annotation, active thesis, active recommendation, active chart mode, indicators, user preferences.
Do not persist temporary viewport state unless required. Persist reusable chart layouts and user chart preferences.

============================================================
48. REAL-TIME KLINECHART UPDATES
============================================================

WebSocket → Frontend market-data store → ChartDataAdapter → KLineChartAdapter → KLineChart.

Distinguish NEW_CANDLE from CANDLE_UPDATED from PRICE_UPDATED.
Do not recreate the entire chart for every price update. Use incremental updates. Avoid unnecessary React re-renders. The chart must remain smooth during real-time updates.

============================================================
49. KLINECHART TIMEFRAME MANAGEMENT
============================================================

Support: 1D, 4H, 1H, 30M, 15M, 5M, 1M.
The timeframe selector must synchronize with: market data requests, AI analysis context, chart state, WebSocket subscriptions, recommendation context, thesis context.

On timeframe change: update chart timeframe → resolve candle data → update KLineChart → update analysis context → update visible semantic annotations → preserve annotation market coordinates → re-render through the adapter.

============================================================
50. KLINECHART INDICATORS
============================================================

Indicators where appropriate: MA, EMA, SMA, ATR, RSI, MACD, Bollinger Bands, volume where available.
Indicators are supporting evidence, never the sole decision source. The AI must not hallucinate indicator values — calculations come from deterministic services; the renderer displays validated output.

============================================================
51. KLINECHART PERFORMANCE
============================================================

Avoid: unnecessary chart recreation, unnecessary React renders, reprocessing all candles per tick, recreating all annotations when one changes, excessive WebSocket messages, duplicated market data, expensive UI-thread calculations.
Use: memoization, incremental updates, efficient state management, batched annotation updates, throttled visual updates, cached historical candles, virtualized/non-blocking patterns.
The chart must remain responsive during live updates, AI streaming, annotation updates, timeframe switching, and interaction.

============================================================
52. CHART ANNOTATION LIFECYCLE
============================================================

States: CREATED, ACTIVE, UPDATED, HIDDEN, INVALIDATED, EXPIRED, REMOVED.
Annotations link to their source: analysis_id, recommendation_id, thesis_id, agent_run_id, workspace_id. Annotations are tenant/workspace scoped.

============================================================
53. CHART VERSIONING
============================================================

When an AI analysis changes, do not blindly overwrite historical chart state. Support versioned analysis/chart states:
Analysis V1 → Chart State V1 → Thesis changes → Analysis V2 → Chart State V2.
This lets users understand how the AI thesis evolved.

============================================================
54. MCP SERVER
============================================================

Create leovee-mcp using modelcontextprotocol/ext-apps as the foundation for MCP App-compatible experiences.

Example MCP tools:
market.get_snapshot, market.get_candles, market.get_price, market.get_multi_timeframe,
analysis.run, analysis.get, analysis.explain,
research.search, research.get,
recommendation.get, recommendation.list,
thesis.get, thesis.validate,
chart.get_annotations, chart.get_analysis,
memory.search, memory.get_symbol_profile, memory.get_strategy_stats, memory.get_lessons,
workspace.get, workspace.context, watchlist.get.

============================================================
55. MCP SECURITY
============================================================

MCP must respect the same authentication, authorization, workspace isolation, tenant isolation, rate limits, and audit logging.
Never allow an MCP client to access another user's workspace. Never expose API keys, broker credentials, internal database credentials, or private secrets.

============================================================
56. MCP APP EXPERIENCE
============================================================

Where appropriate, create MCP Apps that display: trading charts (KLineChart-powered where supported), recommendations, market analysis, thesis state, research, memory insights, watchlists.
The UI must use the same backend APIs and authorization model. Do not duplicate business logic inside the MCP layer — MCP calls application services.

============================================================
57. USER TRADE SECTION
============================================================

Trades sections: Open, Closed, Pending, Cancelled, Invalidated, Ideas.
Each trade/setup shows: Symbol, Direction, Entry, Stop, TP, R:R, Status, Created, Updated, Thesis, Result.

============================================================
58. RECOMMENDATIONS SECTION
============================================================

Filters: symbol, BUY, SELL, WAIT, NO TRADE, active, invalidated, completed, timeframe.
Recommendation card: symbol, direction, status, entry, SL, TPs, R:R, calibrated confidence, why, invalidation.

============================================================
59. ANALYSIS SECTION
============================================================

Store full market analyses. User can view: market bias, structure, liquidity, zones, volatility, news, scenarios, contradictions, recommendation, chart. Chart views use the KLineChart-based chart engine.

============================================================
60. WATCHLIST
============================================================

Multiple watchlists (e.g. "London Session": EURUSD, GBPUSD, GBPJPY; "US Session": EURUSD, USDJPY, XAUUSD).
Watchlist updates: price, spread, volatility, AI bias, setup state, thesis state.

============================================================
61. ALERTS
============================================================

Alerts for: price, structure, liquidity, volatility, news, recommendation, thesis invalidation, target reached.
Channels: in-app, email, WebSocket, push architecture.

============================================================
62. JOURNAL
============================================================

Journal entries can attach: trade, recommendation, analysis, chart, conversation, thesis.
Fields: title, notes, tags, result, emotion (optional), lesson, timestamp.
User journal lessons can optionally be promoted into agent lesson memory (explicit user action).

============================================================
63. PERFORMANCE
============================================================

Display: total trades, win rate, loss rate, expectancy, average R, profit factor, max drawdown, average risk, average reward, setup quality, AI recommendation accuracy, invalidation accuracy, confidence calibration curve (stated vs realized).
Do not optimize only for win rate.

============================================================
64. BACKTESTING / REPLAY
============================================================

HistoricalReplayEngine — input: historical market state at time T. The agent must not see future information.
Replay: market → analysis → scenario → recommendation → thesis → outcome. Allow replay from the UI.
Replay chart rendering uses the same KLineChart chart engine; the replay renderer only displays data available at time T. Future candles must never be visible to the agent or replay decision logic.
Replay outcomes feed the same memory/learning pipeline, but are tagged source=REPLAY and kept statistically separate from live outcomes.

============================================================
65. DATABASE ARCHITECTURE
============================================================

Core tables:
users, organizations, workspaces, workspace_members, roles, permissions,
subscriptions, plans, usage_records, invoices,
sessions, oauth_accounts,
conversations, messages, message_tool_calls, message_attachments,
symbols, watchlists, watchlist_items,
market_snapshots, candles, market_events,
structures, liquidity_events, price_zones, volatility_states,
news_events, research_items,
agent_runs, agent_traces,
scenarios, theses, recommendations,
trades, trade_outcomes,
agent_episodes, agent_memories, memory_embeddings (pgvector), symbol_profiles, strategy_stats, lessons, calibration_bins, outcome_records,
chart_annotations, chart_layouts, chart_versions,
alerts, notifications,
journal_entries,
platform_secrets, model_configs,
oanda_connections,
api_keys,
mcp_sessions,
audit_logs, system_events.

============================================================
66. TENANT ISOLATION
============================================================

Every tenant-owned table must be scoped (workspace_id). Use database-level safeguards where appropriate; consider PostgreSQL Row Level Security for highly sensitive tenant-owned data (including all memory tables). Never rely only on frontend filtering.

Test that User A cannot access User B's: conversations, trades, workspace, OANDA connection, recommendations, API keys, chart annotations, chart layouts, memories, lessons, strategy statistics.

============================================================
67. ENCRYPTION
============================================================

Encrypt sensitive values: OANDA tokens, provider secrets, API keys, OAuth tokens.
Never log secrets. Never return secrets to frontend. Mask credentials in UI.

============================================================
68. SAAS BILLING
============================================================

Plans: FREE, PRO, PRO_PLUS, ENTERPRISE.
Plan limits can include: AI messages, analyses, research requests, chart analyses, watchlists, alerts, historical data depth, replay, memory retention depth, API calls, MCP calls.

UsageService tracks: tokens, model calls, analysis runs, research runs, chart operations, MCP operations, memory operations.
Never trust usage counters from frontend.

============================================================
69. BILLING ARCHITECTURE
============================================================

Billing abstraction with pluggable payment adapters (see stack section: primary processor + manual/offline adapter).
Entities: Plan, Subscription, Invoice, Usage, Entitlement.
Entitlement checks must happen server-side.

============================================================
70. ADMIN DASHBOARD (reduced operator scope)
============================================================

A separate admin section for the single-operator deployment. The original
28-section admin plane is **intentionally reduced** — unbuilt sections are
not carried as permanent debt.

Required admin surfaces (exit criteria for Phase 36 + operator secrets):
1. **Entitlements** — plan, limits, and subscription status for the workspace
2. **Overview** — high-level platform counts (users/workspaces/conversations)
3. **Conversations** — operator listing of conversations in scope
4. **Observability** — agent-run / memory observability summary
5. **Platform secrets** — SUPER_ADMIN / platform-admin panel to set encrypted
   platform credentials (`platform_secrets`; LLM / Finnhub / practice OANDA).
   Never returns secret values; masks configured state only.

Permission matrix: support vs platform-admin via `/admin/me`; support-only
sections hide client-side ahead of backend 403s.

Sections 71–77 below document optional depth that is **out of scope** for
the current product unless re-opened by the owner. They are not open debt.

============================================================
71. ADMIN OVERVIEW (optional depth — out of scope)
============================================================

Optional depth beyond §70 Overview: total users, active users, active
workspaces, subscriptions, AI/token/market-data/MCP request counts, errors,
latency, jobs, agents, memory store size, learning pipeline health.

============================================================
72. ADMIN USER MANAGEMENT (optional depth — out of scope)
============================================================

Optional: search/inspect/suspend/activate users, reset sessions, usage,
subscription, workspace, audit history. Permission boundaries still apply
if this surface is re-opened.

============================================================
73. ADMIN WORKSPACE MANAGEMENT (optional depth — out of scope)
============================================================

Optional: search workspace, inspect metadata, subscription, usage, members,
status, limits, feature flags. Avoid exposing private chat/memories unless
explicitly authorized.

============================================================
74. ADMIN AI MANAGEMENT (optional depth — out of scope)
============================================================

Optional: configure providers, models, routing, fallbacks, rate limits,
token budgets, system prompts, agent/memory parameters via admin UI.
Provider configuration must not be hard-coded when this surface exists.

============================================================
75. ADMIN MARKET DATA (optional depth — out of scope)
============================================================

Optional: OANDA/stream/API health, latency, rate limits, candle sync,
backfill status, freshness, provider errors.

============================================================
76. ADMIN MCP (optional depth — out of scope)
============================================================

Optional: MCP server status, sessions, requests, errors, latency, tools,
auth failures.

============================================================
77. ADMIN AGENT & MEMORY OBSERVABILITY (optional depth — out of scope)
============================================================

§70 Observability covers the required agent-run summary. Optional depth:
full AgentRun/AgentTrace browsers, calibration curves, strategy decay
flags, per-workspace memory growth. Never expose private chain-of-thought.

============================================================
78. EVENT-DRIVEN ARCHITECTURE
============================================================

Events: MARKET_UPDATED, NEW_CANDLE, STRUCTURE_SHIFT, LIQUIDITY_SWEEP, VOLATILITY_CHANGE, NEWS_EVENT, SPREAD_CHANGE, THESIS_CHANGED, TARGET_REACHED, THESIS_INVALIDATED, OUTCOME_RECORDED, LESSON_CREATED, STRATEGY_DECAY_DETECTED, USER_MESSAGE, ANALYSIS_REQUESTED, CHART_UPDATED, CHART_ANNOTATION_CREATED, CHART_ANNOTATION_UPDATED.
Do not invoke expensive models for every market tick.

============================================================
79. BACKGROUND WORKERS
============================================================

Workers handle: market-data ingestion (stream consumers), candle synchronization and backfill, gap repair, news ingestion, analysis, research, thesis monitoring, outcome recording, learning pipeline (statistics update, calibration, lesson distillation, decay detection), memory maintenance (aging, archiving, embedding generation), alerts, notifications, usage aggregation, cleanup, scheduled tasks.

============================================================
80. CACHING
============================================================

Redis for: market snapshots, recent candles, session state, rate limiting, locks, temporary agent state, streaming, job queues.
Never treat Redis as the permanent source of truth.

============================================================
81. REAL-TIME SYSTEM
============================================================

Frontend connects via WebSocket. Events:
market.updated, price.updated, candle.updated, candle.completed, analysis.started, analysis.completed, recommendation.created, recommendation.updated, thesis.updated, thesis.invalidated, lesson.created, chart.annotation.created, chart.annotation.updated, chart.annotation.removed, alert.triggered, notification.created.
Every WebSocket connection must be authenticated. Every event must be workspace-scoped. Use Redis pub/sub (or Streams) for fan-out so WebSocket delivery works across multiple backend instances.

============================================================
82. FRONTEND ARCHITECTURE
============================================================

src/
  app/
  routes/
  components/
  features/ (auth, dashboard, chat, markets, watchlist, analysis, recommendations, trades, alerts, journal, memory, performance, settings, billing, admin)
  chart/
  api/
  hooks/
  stores/
  websocket/
  types/

The chart feature contains the KLineChart integration behind an internal abstraction. Do not spread KLineChart imports throughout unrelated React components.

============================================================
83. FRONTEND DESIGN
============================================================

Design should feel like a premium AI trading terminal, branded Leovee.
Core UI: left sidebar, main content, optional right analysis panel. Chart is central.
Use: dark/light theme architecture, responsive layout, keyboard shortcuts, loading states, skeletons, empty states, error states, optimistic UI where safe.
KLineChart must be visually integrated — it must not feel like an isolated third-party component.

============================================================
84. CHAT + CHART EXPERIENCE
============================================================

When the user asks "Analyze EURUSD":
1. Open/update EURUSD KLineChart.
2. Fetch market context.
3. Recall relevant memories.
4. Analyze.
5. Generate semantic annotations.
6. Render annotations through KLineChart.
7. Stream AI response.
8. Display recommendation.
9. Store analysis (episode).
10. Create thesis if appropriate.

The user should feel that CHAT and CHART are one unified experience.

============================================================
85. CHAT ACTIONS
============================================================

AI responses may contain structured actions: OPEN_CHART, SET_SYMBOL, SET_TIMEFRAME, DRAW_ANNOTATION, SHOW_RECOMMENDATION, SHOW_RESEARCH, SHOW_THESIS, SHOW_MEMORY.
Frontend executes these through validated application events. Never allow arbitrary frontend code execution from the model. Chart actions are translated into safe semantic operations; the model never executes raw KLineChart commands.

============================================================
86. AI EXPLANATION
============================================================

Never expose raw chain-of-thought. Expose: rationale, evidence, assumptions, uncertainty, contradictions, decision factors, invalidation, memory citations (which past episodes/lessons informed this analysis).

============================================================
87. NO HALLUCINATION
============================================================

The agent must NEVER invent: price, candle, indicator, news, economic event, entry, stop, target, historical statistics, win rates, or memories.
If unavailable: DATA_UNAVAILABLE. If evidence is insufficient: INSUFFICIENT_EVIDENCE. If memory sample is too small: LOW_SAMPLE.

============================================================
88. SOURCE PROVENANCE
============================================================

Every important fact must have: source, timestamp, provider, timeframe, confidence.
Memory-derived facts must additionally carry: episode references, sample size, freshness.

Example:
{ "type": "market_structure", "source": "MarketStructureEngine", "timeframe": "15M", "timestamp": "...", "confidence": 0.91 }

============================================================
89. API ARCHITECTURE
============================================================

REST:
/api/v1/auth, /api/v1/users, /api/v1/workspaces, /api/v1/conversations, /api/v1/messages, /api/v1/markets, /api/v1/analysis, /api/v1/recommendations, /api/v1/trades, /api/v1/theses, /api/v1/watchlists, /api/v1/alerts, /api/v1/research, /api/v1/memory, /api/v1/journal, /api/v1/performance, /api/v1/billing, /api/v1/settings.

Admin:
/api/v1/admin/users, /api/v1/admin/workspaces, /api/v1/admin/usage, /api/v1/admin/models, /api/v1/admin/providers, /api/v1/admin/oanda, /api/v1/admin/mcp, /api/v1/admin/agents, /api/v1/admin/memory, /api/v1/admin/audit, /api/v1/admin/system.

WebSocket: /api/v1/ws

============================================================
90. API SECURITY
============================================================

Implement: authentication, authorization, request validation, rate limiting, input sanitization, CORS, security headers, audit logging, idempotency for sensitive operations.

============================================================
91. API KEY MANAGEMENT
============================================================

User API keys must: be hashed, be shown only once, support scopes, support revocation, have expiration, be auditable.
Example scopes: market.read, analysis.read, analysis.write, recommendation.read, trade.read, memory.read, mcp.read.

============================================================
92. OBSERVABILITY
============================================================

Structured logging. Track: request ID, user ID, workspace ID, agent run ID, model, provider, latency, tokens, tool calls, errors.
Metrics: API latency, LLM latency, LLM cost, market-data latency, OANDA errors, stream uptime, WebSocket connections, queue depth, Redis health, database latency, agent success rate, memory retrieval latency, learning pipeline lag, KLineChart rendering/update performance where measurable.

============================================================
93. AUDIT LOG
============================================================

Audit: login, logout, password changes, OANDA connection, API key creation/revocation, billing changes, subscription changes, admin actions, trade execution, recommendation changes, permission changes, memory deletion/editing by users, chart annotation changes where relevant.
Every record: actor, action, resource, resource_id, timestamp, IP where appropriate, metadata.

============================================================
94. SECURITY BOUNDARIES
============================================================

Never allow:
User A → User B data.
Workspace A → Workspace B data (including memories, lessons, statistics).
MCP client → unauthorized workspace.
LLM → raw database.
LLM → unvalidated memory writes.
Frontend → secrets.
Model → arbitrary code execution.
Chart annotation → arbitrary JavaScript.
Model → raw KLineChart API execution.

============================================================
95. FAILURE HANDLING
============================================================

Market data unavailable → NO_TRADE.
News unavailable → lower confidence.
Spread abnormal → WAIT.
Conflicting timeframes → WAIT / NO_TRADE.
Risk calculation failure → NO_TRADE.
LLM unavailable (no provider configured, or all failover providers fail) →
**NO_TRADE** with reason `LLM_UNAVAILABLE`. Never emit BUY/SELL with a
confidence value when the LLM / narrative layer did not run. Prefer failover
across configured providers first; if none can run, fail closed.
Adversarial validation cannot run → **NO_TRADE** with reason
`ADVERSARIAL_UNAVAILABLE` (same fail-closed rule).
Chart failure → recommendation survives.
Database failure → fail safely.
OANDA failure → do not fabricate data.
OANDA stream disconnect → documented REST fallback + gap backfill on reconnect.
Memory system failure → agent continues without memory (degraded mode, labeled), never blocks analysis, never fabricates memories.
KLineChart rendering failure → preserve analysis/recommendation state, attempt safe chart recovery, never fabricate chart data.

============================================================
96. PROJECT STRUCTURE
============================================================

Backend:
backend/app/
  api/ (routes, websocket)
  core/ (config, security, logging, errors)
  domain/ (market, structure, liquidity, zones, volatility, risk, scenario, thesis, recommendation, chart, memory, users, workspaces, billing)
  agents/ (orchestrator, …)
  engines/ (market_intelligence, scenario, decision, risk, chart_composition, monitoring, learning, reasoning)
  providers/ (llm/anthropic, llm/openai, llm/openrouter, market/oanda, news, calendar, email, payments)
  services/ (auth, workspace, chat, analysis, recommendation, thesis, trade, memory, billing, usage, notification, learning/memory_writer)
  infrastructure/ (database, redis, queues, storage, embeddings)
  mcp/ (server, tools, resources, apps)
  workers/
  models/
  schemas/
  tests/

Frontend:
frontend/src/
  app/, routes/, components/
  features/ (auth, dashboard, chat, markets, analysis, recommendations, trades, watchlists, alerts, journal, memory, performance, settings, billing, admin)
  chart/ (KLineChartAdapter, ChartController, ChartDataAdapter, ChartAnnotationRenderer, ChartIndicatorManager, ChartInteractionManager, ChartTimeframeManager)
  api/, hooks/, stores/, websocket/, types/

============================================================
97. DATABASE MIGRATIONS
============================================================

Use Alembic. Every schema change requires a migration. Never modify production schema manually.

============================================================
98. TYPE SAFETY
============================================================

Backend: Pydantic, SQLAlchemy, typing, mypy.
Frontend: TypeScript strict mode.
Shared API schemas should be generated or synchronized where possible. Chart semantic types and memory record types must be strongly typed.

============================================================
99. TESTING
============================================================

Unit tests: market structure, liquidity, zones, volatility, risk, position sizing, chart geometry, chart semantic model, KLineChart adapter, chart data normalization, chart annotation lifecycle, state machines, permissions, tenant isolation, session/DST detection, candle aggregation from stream ticks, outcome recording, statistics updates, confidence calibration, memory retrieval ranking, memory decay/aging, LOW_SAMPLE labeling.

Integration tests: market → analysis, analysis → reasoning, reasoning → recommendation, recommendation → chart, chart semantic model → KLineChart adapter, chat → agent, agent → thesis, thesis → monitoring, outcome → learning pipeline → updated statistics → next-run recall, MCP → application service, stream disconnect → fallback → backfill.

============================================================
100. MULTI-TENANT SECURITY TESTS
============================================================

Explicitly test: User A cannot query User B workspace, conversation, recommendation, OANDA token, API key, chart annotations, chart layouts, memories, lessons, or strategy statistics. MCP client cannot escape workspace. Admin permissions are enforced.

============================================================
101. REPLAY TESTING
============================================================

Historical replay must ensure NO FUTURE DATA LEAKAGE. At time T the agent can only access data <= T — including memory: replay recall must only retrieve episodes/lessons whose timestamps are <= T. The KLineChart replay view must obey the same temporal boundary.

============================================================
102. COST CONTROL
============================================================

Do not call expensive models on every candle. Use: event-driven triggers, caching, model routing, context compression, result reuse, incremental context, memory retrieval budgets, rate limits.
No meaningful event → NO LLM CALL. Minor event → FAST MODEL. Major structural event → REASONING MODEL. Major news event → RESEARCH + REASONING.

============================================================
103. FEATURE FLAGS
============================================================

Flags: AI_CHAT, ADVANCED_ANALYSIS, RESEARCH, BACKTEST, MCP, OANDA_EXECUTION, ADVANCED_CHARTS, PREMIUM_MODELS, MEMORY, LEARNING, CROSS_TENANT_AGGREGATE_LEARNING (default OFF).
Feature flags must be enforced server-side.

**`OANDA_EXECUTION` note:** this is a **deploy / server policy gate**, not a
Settings UI field. Live order placement is rejected in `trade_service` when
`execution_enabled=True`; staging deploy scripts force practice OANDA and
`OANDA_EXECUTION=false`. Do not present it as a user-toggleable product setting
until live execution is explicitly authorized.

============================================================
104. ADMIN FEATURE CONTROL
============================================================

Admin can enable/disable: features, providers, models, instruments, analysis modes, MCP, execution, memory/learning parameters. Use safe defaults.

============================================================
105. NOTIFICATIONS
============================================================

Notification { user_id, workspace_id, type, title, message, severity, resource_type, resource_id, read, created_at }.
Types: RECOMMENDATION_CREATED, THESIS_INVALIDATED, TARGET_REACHED, PRICE_ALERT, NEWS_ALERT, LESSON_CREATED, STRATEGY_DECAY, SYSTEM_ALERT.

============================================================
106. USER SETTINGS
============================================================

Settings: Profile, Security, Workspace, AI Preferences, Default Model, Default Timeframes, Chart Preferences, Risk Preferences, Memory Preferences (retention, what the agent may remember, view/delete controls), Notifications, OANDA, API Keys, Billing.

Chart Preferences: default chart type, default timeframe, visible indicators, annotation visibility, crosshair preferences, chart layout, price scale preferences, session display preferences.

============================================================
107. WORKSPACE SETTINGS
============================================================

Workspace defines: default symbols, default timeframes, risk defaults, AI preferences, memory preferences, chart layout, notification preferences, allowed features.

============================================================
108. AI PERSONALIZATION
============================================================

The AI remembers workspace-level preferences (preferred timeframe, analysis style, chart annotations, response style). These preferences are stored in workspace/user memory, separately from market facts.

============================================================
109. RECOMMENDATION LIFECYCLE
============================================================

DETECTED → ANALYZING → FORMING → WAITING_CONFIRMATION → READY → ACTIVE → STRENGTHENING / WEAKENING → TARGET_REACHED or INVALIDATED or EXPIRED.
Every terminal state emits OUTCOME_RECORDED and triggers the learning pipeline.

============================================================
110. COMPLETE EXAMPLE
============================================================

User: "Analyze EURUSD"

System:
1. Identify workspace. 2. Authenticate user. 3. Load workspace preferences. 4. Load recent conversation context.
5. RECALL: retrieve EURUSD symbol profile, similar past episodes, relevant lessons, strategy stats for candidate setups.
6. Fetch OANDA market data. 7. Validate data. 8. Load multi-timeframe candles. 9. Open/update KLineChart.
10. Analyze 4H, 1H, 15M, 5M. 11. Detect liquidity. 12. Detect zones. 13. Analyze volatility. 14. Check upcoming events.
15. Determine missing research. 16. Research.
17. Generate bullish, bearish, and no-trade scenarios. 18. Run adversarial validation (including lesson memory check).
19. Calculate risk. 20. Decision with calibrated confidence.
21. Generate ChartSemanticModel. 22. Validate semantic annotations. 23. Render approved annotations through KLineChart.
24. Store the full episode in memory.

If confirmation missing: WAITING_CONFIRMATION.
The chart is annotated with: HTF structure, liquidity, zones, possible entry, invalidation, targets.
The conversation receives: MARKET BIAS, STATUS, WHY, INVALIDATION, and memory citations.

Later: a 5M STRUCTURE_SHIFT event → re-evaluate thesis → READY or NO_TRADE.
When the thesis reaches a terminal state: outcome recorded → statistics updated → confidence recalibrated → lessons distilled → future EURUSD analyses recall this episode.
KLineChart updates only the affected candle/annotations instead of rebuilding the chart.

============================================================
111. FINAL ARCHITECTURE
============================================================

React UI (TypeScript)
  ↓ REST / WebSocket
FastAPI API Layer
  ↓
AI Agent Orchestrator | Application Services | MCP Server / Apps
  ↓
Domain Engines: Market Intelligence, Structure, Liquidity, Zones, Volatility, Scenario, Risk, Decision, Chart Semantic Model, Thesis, Memory & Learning
  ↓
Anthropic SDK | OpenAI SDK | OANDA v20 (REST + Stream) | News/Calendar Provider | Email Provider | Payment Provider
  ↓
Market Data Normalization → WebSocket → Chart Data Adapter → KLineChart Adapter → KLineChart

Infrastructure: PostgreSQL (+pgvector), Redis, Background Workers, Object Storage.

============================================================
112. DEPLOYMENT & OPERATIONS
============================================================

Produce DEPLOYMENT.md and working deployment assets:
- Dockerfiles for backend, frontend, workers, MCP server; docker-compose for full-stack local and single-server production deployment.
- Environment variable reference (.env.example) with every secret and config documented; secrets never committed.
- Reverse proxy + TLS (e.g. Caddy or Nginx + certbot) configuration.
- Database migration execution strategy on deploy; backup and restore procedure for PostgreSQL (including pgvector data); Redis persistence settings.
- Health-check endpoints for every service; readiness/liveness distinction.
- CI pipeline: lint (ruff, eslint), type check (mypy, tsc), tests, build, image publish. Deployment step documented even if manually triggered.
- Log aggregation and error tracking (e.g. structured logs to file/stdout + Sentry-compatible error reporting abstraction).
- Zero-data-loss deploy expectations: graceful shutdown of workers and stream consumers, WebSocket reconnect handling on deploy.

============================================================
113. IMPLEMENTATION PHASES
============================================================

Do NOT implement everything in one pass. All phases are in scope for production — none are optional.

PHASE 1  Design documents (section 2)
PHASE 2  Project scaffolding + CI + Docker
PHASE 3  Multi-tenant foundation
PHASE 4  Authentication
PHASE 5  Database + migrations (incl. pgvector)
PHASE 6  Workspace system
PHASE 7  OANDA integration (REST + streaming + backfill)
PHASE 8  Market data normalization + candle storage/retention
PHASE 9  Market intelligence
PHASE 10 Multi-timeframe engine
PHASE 11 Structure / liquidity / zones / volatility engines
PHASE 12 Scenario engine
PHASE 13 Risk engine
PHASE 14 News/calendar providers + research agent
PHASE 15 Anthropic integration
PHASE 16 OpenAI integration
PHASE 17 Model router
PHASE 18 Reasoning + adversarial validation
PHASE 19 Decision engine
PHASE 20 Memory foundation (episodes, storage, retrieval, embeddings)
PHASE 21 Learning pipeline (outcomes, statistics, calibration, lessons, decay)
PHASE 22 Thesis system + monitoring
PHASE 23 Chart semantic engine
PHASE 24 KLineChart integration
PHASE 25 Chart renderer and annotation system
PHASE 26 Chat system (with RECALL integration)
PHASE 27 Recommendations
PHASE 28 Trades
PHASE 29 Watchlists
PHASE 30 Alerts
PHASE 31 Journal
PHASE 32 Memory UI section
PHASE 33 Performance (incl. calibration curve)
PHASE 34 MCP server
PHASE 35 MCP Apps
PHASE 36 Admin dashboard (incl. memory observability)
PHASE 37 Billing + payments
PHASE 38 Usage limits + entitlements
PHASE 39 Observability
PHASE 40 Security hardening
PHASE 41 Replay/backtesting (memory-aware, no future leakage)
PHASE 42 Deployment assets + production testing
PHASE 43 Launch readiness review

============================================================
114. IMPLEMENTATION RULE
============================================================

After every phase:
1. Run tests. 2. Run type checks. 3. Run lint. 4. Verify tenant isolation. 5. Verify API contracts. 6. Verify security. 7. Document changes. 8. Do not silently break existing functionality.

For chart-related phases additionally verify: KLineChart integration, normalized candle data, real-time candle updates, timeframe switching, annotation rendering, annotation lifecycle, chart geometry, chart performance, chart recovery after errors, no business logic inside the chart renderer.

For memory-related phases additionally verify: workspace scoping of all memory records, schema validation of all writes, retrieval provenance, LOW_SAMPLE labeling, calibration correctness, decay behavior, replay temporal boundaries, user view/delete controls.

============================================================
115. PRODUCTION REQUIREMENTS
============================================================

Leovee must be: multi-tenant, secure, scalable, observable, fault tolerant, event-driven, asynchronous where appropriate, real-time, AI-powered, market-data driven, memory-equipped, continuously learning, auditable, explainable, backtestable, MCP-compatible, SaaS-ready, KLineChart-powered, performant under real-time market updates.

============================================================
116. FINAL PRINCIPLE
============================================================

The objective is NOT: "Build an AI that predicts the market."

The objective is: "Build Leovee — a production-grade AI market analyst SaaS that continuously observes markets, researches relevant information, generates competing scenarios, challenges its own assumptions, calculates risk deterministically, produces transparent recommendations with calibrated confidence, draws its thesis on the chart like a professional analyst, remembers every analysis and outcome, learns from its own track record, and continuously validates or invalidates its theses."

The chart is a first-class part of the product. KLineChart is the primary chart rendering engine. The AI must not directly control the chart renderer:
AI reasoning → structured semantic chart instructions → validated chart state → KLineChart renderer.

Memory is a first-class part of the product. The learning path is always:
Deterministic outcome recording → statistics → calibration → distilled lessons → retrieval as labeled evidence.
Memory informs decisions; it never replaces live data.

The system must optimize for BETTER DECISIONS, not MORE TRADES.

The agent must always be allowed to say: WAIT, NO TRADE, INSUFFICIENT EVIDENCE, DATA UNAVAILABLE, LOW SAMPLE, THESIS INVALIDATED — and these must be treated as successful, valid outcomes.

============================================================
117. FIRST ACTION
============================================================

DO NOT WRITE APPLICATION CODE YET.

This is a greenfield build. Start by producing:
1. ARCHITECTURE.md
2. DATABASE_SCHEMA.md
3. AGENT_ARCHITECTURE.md
4. MEMORY_ARCHITECTURE.md
5. MCP_ARCHITECTURE.md
6. SAAS_ARCHITECTURE.md
7. DEPLOYMENT.md
8. IMPLEMENTATION_PLAN.md

MEMORY_ARCHITECTURE.md must specify: memory types and schemas, the learning pipeline, calibration methodology, retrieval design (structured + pgvector hybrid), guardrails, decay/aging, replay temporal isolation, and the user-facing memory controls.

Only after these documents are reviewed should implementation begin, following the phases in order.
