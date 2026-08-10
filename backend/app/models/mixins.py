import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class WorkspaceOwnedMixin:
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
