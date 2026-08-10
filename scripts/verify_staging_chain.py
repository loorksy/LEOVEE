#!/usr/bin/env python3
"""End-to-end staging verification against a live API (DEPLOYMENT.md §16.1 / launch readiness)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from typing import Any

import httpx

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
COMPOSE_DIR = os.environ.get("LEOVEE_ROOT", "/opt/leovee")
EMAIL = os.environ.get("VERIFY_EMAIL", f"staging-chain-{uuid.uuid4().hex[:10]}@verify.leovee.local")
PASSWORD = os.environ.get("VERIFY_PASSWORD", "StagingChainPass1!")


def _headers(token: str, tenant_id: str, workspace_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": tenant_id,
        "X-Workspace-Id": workspace_id,
    }


def _psql(sql: str) -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.staging.yml",
        "-f",
        "docker-compose.agent.yml",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "leovee",
        "-d",
        "leovee",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    subprocess.run(cmd, cwd=COMPOSE_DIR, check=True, capture_output=True, text=True)


def main() -> int:
    report: dict[str, Any] = {"api_url": API_URL, "email": EMAIL}
    with httpx.Client(base_url=API_URL, timeout=120.0) as client:
        signup = client.post(
            "/api/v1/auth/signup",
            json={"email": EMAIL, "password": PASSWORD},
        )
        signup.raise_for_status()
        tokens = signup.json()
        report["signup_access_token_prefix"] = tokens["access_token"][:16]

        _psql(
            f"UPDATE users SET status='ACTIVE', email_verified_at=NOW() "
            f"WHERE email='{EMAIL.lower()}';"
        )

        login = client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        login.raise_for_status()
        access = login.json()["access_token"]

        tenant = client.get("/api/v1/me/tenant", headers={"Authorization": f"Bearer {access}"})
        tenant.raise_for_status()
        tj = tenant.json()
        tenant_id = tj["tenant_id"]
        workspace_id = tj["workspace_id"]
        report["tenant_id"] = tenant_id
        report["workspace_id"] = workspace_id
        report["role"] = tj["role"]

        analysis1 = client.post(
            "/api/v1/analysis/run",
            headers=_headers(access, tenant_id, workspace_id),
            json={"symbol": "EURUSD", "timeframe": "H1", "complete_pipeline": True},
        )
        analysis1.raise_for_status()
        a1 = analysis1.json()
        report["analysis1"] = {
            "recommendation_id": a1.get("recommendation_id"),
            "thesis_id": a1.get("thesis_id"),
            "recall_count": len((a1.get("recall") or {}).get("memories") or []),
        }
        rec_id = a1["recommendation_id"]
        thesis_id = a1["thesis_id"]

        rec_get = client.get(
            f"/api/v1/recommendations/{rec_id}",
            headers=_headers(access, tenant_id, workspace_id),
        )
        rec_get.raise_for_status()
        current_status = rec_get.json()["status"]
        report["recommendation_status_after_analysis"] = current_status

        path_to_active = []
        if current_status != "ACTIVE":
            if current_status == "READY":
                path_to_active = ["ACTIVE"]
            else:
                path_to_active = ["READY", "ACTIVE"]
        for status in [*path_to_active, "TARGET_REACHED"]:
            patch = client.patch(
                f"/api/v1/recommendations/{rec_id}/status",
                headers=_headers(access, tenant_id, workspace_id),
                json={"status": status, "facts": {"staging_verify": True}},
            )
            patch.raise_for_status()
            body = patch.json()
            report[f"transition_{status}"] = body.get("terminal_outcome_recorded")

        analysis2 = client.post(
            "/api/v1/analysis/run",
            headers=_headers(access, tenant_id, workspace_id),
            json={"symbol": "EURUSD", "timeframe": "H1", "complete_pipeline": True},
        )
        analysis2.raise_for_status()
        a2 = analysis2.json()
        memories = (a2.get("recall") or {}).get("memories") or []
        report["analysis2_recall"] = memories[:3]
        report["analysis2_recall_count"] = len(memories)

    print(json.dumps(report, indent=2, default=str))
    if report["analysis2_recall_count"] < 1:
        print("FAIL: expected recalled memory after outcome pipeline", file=sys.stderr)
        return 1
    if not report["analysis1"]["thesis_id"]:
        print("FAIL: thesis not created", file=sys.stderr)
        return 1
    print("OK: staging chain verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
