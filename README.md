# Leovee

Production-grade multi-tenant AI Forex trading analyst SaaS.

## Design

See `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, and related docs in the repository root.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/health/live  
- Web: http://localhost:3000  

## Local development

**Backend:**

```bash
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend && npm ci && npm run dev
```

## BabyClaw manager

Self-hosted BabyClaw env manager (VPS API + Flutter app) lives in `babyclaw-manager/`. See `babyclaw-manager/README.md`.

## License

Proprietary — Leovee.
