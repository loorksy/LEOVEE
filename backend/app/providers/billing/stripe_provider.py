from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.providers.billing.base import BillingProvider
from app.providers.billing.manual import ManualBillingProvider
from app.services import billing_service


class StripeBillingProvider(BillingProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def create_checkout_session(
        self,
        *,
        tenant_id: str,
        plan_code: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        import stripe

        stripe.api_key = self._settings.stripe_secret_key
        session = stripe.checkout.Session.create(
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": f"Leovee {plan_code}"},
                        "unit_amount": 2900,
                        "recurring": {"interval": "month"},
                    },
                    "quantity": 1,
                }
            ],
            metadata={"tenant_id": tenant_id, "plan_code": plan_code},
        )
        return {"provider": "stripe", "checkout_url": session.url, "session_id": session.id}

    async def handle_webhook(
        self,
        session: AsyncSession,
        payload: bytes,
        signature: str | None,
    ) -> dict[str, Any]:
        import stripe

        stripe.api_key = self._settings.stripe_secret_key
        # Both are Optional in settings but mandatory for verification. Passing
        # None through would either raise deep inside the SDK or, worse, skip
        # the signature check — an unauthenticated caller could then forge
        # billing events.
        if signature is None:
            raise ValueError("Stripe webhook is missing its signature header")
        webhook_secret = self._settings.stripe_webhook_secret
        if not webhook_secret:
            raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            webhook_secret,
        )
        event_id = str(event["id"])
        event_type = str(event["type"])
        is_new, _row = await billing_service.record_webhook_event(
            session,
            provider="stripe",
            external_event_id=event_id,
            event_type=event_type,
            payload=dict(event),
        )
        if not is_new:
            return {"provider": "stripe", "duplicate": True, "id": event_id}
        if event_type == "checkout.session.completed":
            data = event["data"]["object"]
            metadata = data.get("metadata") or {}
            await billing_service.apply_entitlement_from_checkout(
                session,
                tenant_id=str(metadata.get("tenant_id", "")),
                plan_code=str(metadata.get("plan_code", "PRO")),
            )
        return {"provider": "stripe", "type": event_type, "id": event_id, "processed": True}


class TestStripeBillingProvider(BillingProvider):
    """Deterministic webhook handling for tests without Stripe SDK verification."""

    async def create_checkout_session(
        self,
        *,
        tenant_id: str,
        plan_code: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        return {"provider": "test_stripe", "tenant_id": tenant_id, "plan_code": plan_code}

    async def handle_webhook(
        self,
        session: AsyncSession,
        payload: bytes,
        signature: str | None,
    ) -> dict[str, Any]:
        data = json.loads(payload.decode("utf-8"))
        event_id = str(data["id"])
        event_type = str(data["type"])
        is_new, _row = await billing_service.record_webhook_event(
            session,
            provider="stripe",
            external_event_id=event_id,
            event_type=event_type,
            payload=data,
        )
        if not is_new:
            return {"provider": "stripe", "duplicate": True, "id": event_id}
        if event_type == "checkout.session.completed":
            obj = data.get("data", {}).get("object", {})
            metadata = obj.get("metadata") or {}
            await billing_service.apply_entitlement_from_checkout(
                session,
                tenant_id=str(metadata.get("tenant_id", "")),
                plan_code=str(metadata.get("plan_code", "PRO")),
            )
        return {"provider": "stripe", "processed": True, "id": event_id}


def get_billing_provider(settings: Settings | None = None) -> BillingProvider:
    settings = settings or get_settings()
    if settings.billing_provider == "test_stripe":
        return TestStripeBillingProvider()
    if settings.billing_provider == "stripe" and settings.stripe_secret_key:
        return StripeBillingProvider(settings)
    return ManualBillingProvider()
