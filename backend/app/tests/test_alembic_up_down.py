from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import create_engine, text


def test_alembic_upgrade_and_downgrade_on_clean_schema(postgres_migration_url: str) -> None:
    """Phase 5/42: migration up then down one revision on a clean database."""
    sync_url = postgres_migration_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    engine.dispose()

    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["DATABASE_MIGRATION_URL"] = postgres_migration_url
    backend = os.path.join(os.path.dirname(__file__), "..", "..")

    up = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert up.returncode == 0, up.stderr

    down = subprocess.run(
        ["alembic", "downgrade", "-1"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert down.returncode == 0, down.stderr

    # Restore head for other tests that share the session-scoped DB.
    restore = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert restore.returncode == 0, restore.stderr
