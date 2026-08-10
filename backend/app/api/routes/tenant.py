from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_tenant_context
from app.core.tenant import TenantContext

router = APIRouter(prefix="/api/v1", tags=["tenant"])


@router.get("/me/tenant")
async def get_my_tenant(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> dict[str, str]:
    return {
        "tenant_id": str(tenant.tenant_id),
        "user_id": str(tenant.user_id),
        "workspace_id": str(tenant.workspace_id),
        "role": tenant.role.value,
    }
