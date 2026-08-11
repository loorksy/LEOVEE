# §114 checklist — PR phase 41 (replay / backtesting)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] `HistoricalReplayEngine` + `POST /api/v1/replay/preview`
- [x] Temporal memory recall (`created_at` / `occurred_at` <= T)
- [x] §101 `test_replay_temporal_s101.py` — no future candle or memory leakage
- [x] Frontend `filterCandlesForReplay` + `ReplayPanel` components
- [x] Replay UI route — `ReplayPage` at `/replay` in `App.tsx` + AppShell nav; smoke `ReplayPage.test.tsx`
