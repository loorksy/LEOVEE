from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_context, get_workspace_context
from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.providers.billing.stripe_provider import get_billing_provider
from app.services import entitlement_service

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=32)
    success_url: str
    cancel_url: str


@router.get("/entitlements")
async def get_entitlements(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    return await entitlement_service.entitlements_for_tenant(session, tenant)


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> dict[str, Any]:
    provider = get_billing_provider()
    return await provider.create_checkout_session(
        tenant_id=str(tenant.tenant_id),
        plan_code=body.plan_code,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
    )


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.billing_provider not in {"stripe", "test_stripe"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe not enabled")
    payload = await request.body()
    provider = get_billing_provider(settings)
    return await provider.handle_webhook(session, payload, stripe_signature)
