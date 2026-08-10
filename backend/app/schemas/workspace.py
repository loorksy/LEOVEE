from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceSummary(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    slug: str
    owner_user_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceSummary]


class WorkspaceDetailResponse(WorkspaceSummary):
    settings_json: dict[str, object] = Field(default_factory=dict)
