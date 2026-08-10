from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.providers.billing.base import BillingProvider
from app.providers.billing.manual import ManualBillingProvider


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

    async def handle_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        import stripe

        stripe.api_key = self._settings.stripe_secret_key
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            self._settings.stripe_webhook_secret,
        )
        return {"provider": "stripe", "type": event["type"], "id": event["id"]}


def get_billing_provider(settings: Settings | None = None) -> BillingProvider:
    settings = settings or get_settings()
    if settings.billing_provider == "stripe" and settings.stripe_secret_key:
        return StripeBillingProvider(settings)
    return ManualBillingProvider()
