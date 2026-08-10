from __future__ import annotations

from typing import Any

from app.providers.billing.base import BillingProvider


class ManualBillingProvider(BillingProvider):
    """Enterprise / manual invoice path — no external checkout."""

    async def create_checkout_session(
        self,
        *,
        tenant_id: str,
        plan_code: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        return {
            "provider": "manual",
            "tenant_id": tenant_id,
            "plan_code": plan_code,
            "status": "pending_invoice",
            "message": "Contact sales to activate this plan.",
        }

    async def handle_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        return {"provider": "manual", "ignored": True}
