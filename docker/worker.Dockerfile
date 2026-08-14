#syntax=docker/dockerfile:1
# Worker image — same as API; Arq settings added in a later phase.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md ./
COPY backend/app ./app

RUN pip install --upgrade pip && pip install .

RUN useradd --create-home --shell /bin/bash leovee
USER leovee

# Liveness for a hung arq worker (no HTTP port to probe). redis-cli is not in this
# image (python:3.12-slim); redis-py is installed as a dependency, so ping via python.
# Reaching REDIS_URL is a proxy for "the worker process is alive and its deps import".
# (arq --check is unsuitable: WorkerSettings leaves health_check_interval at the 3600s
# default, so the health key is absent for the first hour after every start.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import redis, os; redis.from_url(os.environ['REDIS_URL']).ping()"

CMD ["arq", "app.workers.settings.WorkerSettings"]
