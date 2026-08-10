# §114 checklist — PR phase 41 (replay / backtesting)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] `HistoricalReplayEngine` + `POST /api/v1/replay/preview`
- [ ] Temporal memory recall (`created_at` / `occurred_at` <= T)
- [ ] §101 `test_replay_temporal_s101.py` — no future candle or memory leakage
- [ ] Frontend `filterCandlesForReplay` + `ReplayPanel`
