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

CMD ["python", "-c", "import time; print('leovee-worker placeholder — Arq worker starts in a later phase'); time.sleep(86400)"]
