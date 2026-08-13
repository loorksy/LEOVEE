"""Linking a Telegram account to a workspace, and the one-time code that does it.

Two tables and one asymmetry worth stating: the **link** is workspace-scoped and
lives as long as the user wants it, while the **code** is workspace-scoped and
lives for minutes. They are separate rows because they answer different
questions — "who is this sender" and "may this sender become that user" — and a
single row would have to be both a credential and an identity.

``telegram_user_id`` is globally unique, deliberately. One Telegram account maps
to at most one workspace, so an inbound message resolves to exactly one tenant
with no ambiguity to break. Allowing two would mean asking the sender which
workspace they meant, in a channel where the answer is untrusted text.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.mixins import WorkspaceOwnedMixin

__all__ = ["TelegramLink", "TelegramLinkCode"]


class TelegramLink(Base, WorkspaceOwnedMixin, TimestampMixin):
    __tablename__ = "telegram_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    #: Telegram ids exceed 32 bits, so BigInteger rather than Integer.
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    #: Where to reply. Equal to the user id for a direct chat, but stored
    #: separately because they are different identifiers and only one of them
    #: is an address.
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    #: Unlinking keeps the row and stamps it: a compromised account is revoked
    #: by the platform, and the record of when matters more than the row's
    #: absence would.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class TelegramLinkCode(Base, WorkspaceOwnedMixin, TimestampMixin):
    __tablename__ = "telegram_link_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    #: Stored as a hash, never in the clear. A code is a bearer credential for
    #: the few minutes it lives, and a database read should not be enough to
    #: claim someone's workspace.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Set on use. The row survives so a replay is answered with "already used"
    #: rather than "unknown code" — the same reply either way to the sender, but
    #: the difference is visible to an operator reading the table.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
