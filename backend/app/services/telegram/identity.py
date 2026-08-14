"""Who is this sender, and may they become that user?

Two questions that look alike and are not. Resolution answers "which workspace
does this Telegram id already belong to"; linking answers "may this Telegram id
join that workspace". The first runs on every message; the second runs once, and
only when the sender presents a code they could only have got from inside the
platform.

**Neither can run under workspace RLS**, and that is the crux. A webhook arrives
carrying a Telegram user id and nothing else — the workspace is the *answer* to
the lookup, not an input to it. Binding RLS from the message would mean letting
untrusted text name the workspace it wants, which is the exact escape the whole
tenancy model exists to prevent. So both go through narrow `SECURITY DEFINER`
functions that take one argument, return a fixed projection, and cannot
enumerate. Everything downstream runs under ordinary RLS bound to whatever they
returned.

**The code is hashed at rest.** For the minutes it lives it is a bearer
credential for a workspace, and a database read should not be enough to claim
someone's account.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.telegram import TelegramLinkCode

__all__ = [
    "LINK_CODE_TTL",
    "LINK_CODE_ALPHABET",
    "LINK_CODE_LENGTH",
    "LinkResolution",
    "IssuedCode",
    "issue_link_code",
    "consume_link_code",
    "resolve_sender",
    "revoke_link",
    "hash_code",
]

#: Ten minutes. Long enough to switch apps and paste, short enough that a code
#: read over someone's shoulder is worthless by the time it is used.
LINK_CODE_TTL = timedelta(minutes=10)

#: No 0/O/1/I/L: the code is read off one screen and typed into another, and a
#: character pair that cannot be told apart turns a security control into a
#: support ticket.
LINK_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LINK_CODE_LENGTH = 8


def hash_code(code: str) -> str:
    """SHA-256 of the normalised code.

    Normalised before hashing — upper-cased and stripped — because the user
    retypes it, and a code that fails on a trailing space is indistinguishable
    from a wrong code to the person holding it.
    """
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedCode:
    #: Shown once, never stored. There is no way to retrieve it afterwards.
    code: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LinkResolution:
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    chat_id: int

    async def to_tenant_context(self, session: AsyncSession) -> TenantContext:
        """Rebuild the scope from the database, every message.

        Deliberately not cached on the link row. `resolve_tenant_context`
        verifies membership rather than trusting stored ids, so a user removed
        from the workspace loses their Telegram access on the very next message
        — automatically, with nothing to remember to revoke. A cached context
        would keep answering them.
        """
        return await resolve_tenant_context(session, self.user_id)


async def issue_link_code(
    session: AsyncSession, tenant: TenantContext, *, user_id: uuid.UUID | None = None
) -> IssuedCode:
    """Mint a one-time code inside the platform, where the user is authenticated."""
    await bind_workspace_rls(session, tenant)
    code = "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(LINK_CODE_LENGTH))
    expires_at = datetime.now(UTC) + LINK_CODE_TTL
    session.add(
        TelegramLinkCode(
            id=uuid.uuid4(),
            tenant_id=tenant.tenant_id,
            workspace_id=tenant.workspace_id,
            code_hash=hash_code(code),
            user_id=user_id or tenant.user_id,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return IssuedCode(code=code, expires_at=expires_at)


async def resolve_sender(session: AsyncSession, telegram_user_id: int) -> LinkResolution | None:
    """Which workspace this Telegram account belongs to, or nothing."""
    row = (
        await session.execute(
            text("SELECT * FROM resolve_telegram_link(:tg)"), {"tg": telegram_user_id}
        )
    ).first()
    if row is None or row.user_id is None:
        # A link with no user cannot be re-verified against membership, so it
        # cannot be trusted to still be valid. Treated as unlinked.
        return None
    return LinkResolution(
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        chat_id=row.chat_id,
    )


async def consume_link_code(
    session: AsyncSession,
    *,
    code: str,
    telegram_user_id: int,
    telegram_chat_id: int,
    username: str | None = None,
) -> LinkResolution | None:
    """Spend a code and bind the account, atomically. None if it was not valid.

    Single-use is enforced in the database, not here: two webhook deliveries of
    the same message can race, and a check-then-write in Python would let both
    win. The consuming UPDATE is what makes exactly one of them succeed.
    """
    consumed = (
        await session.execute(
            text("SELECT * FROM consume_telegram_link_code(:h)"), {"h": hash_code(code)}
        )
    ).first()
    if consumed is None or consumed.user_id is None:
        return None

    await session.execute(
        text(
            "SELECT create_telegram_link(:tenant, :workspace, :user, :tg_user, :tg_chat, :username)"
        ),
        {
            "tenant": consumed.tenant_id,
            "workspace": consumed.workspace_id,
            "user": consumed.user_id,
            "tg_user": telegram_user_id,
            "tg_chat": telegram_chat_id,
            "username": (username or "")[:64] or None,
        },
    )
    return LinkResolution(
        tenant_id=consumed.tenant_id,
        workspace_id=consumed.workspace_id,
        user_id=consumed.user_id,
        chat_id=telegram_chat_id,
    )


async def revoke_link(
    session: AsyncSession, tenant: TenantContext, *, telegram_user_id: int
) -> bool:
    """Cut a linked account off, from inside the platform.

    Whoever holds the Telegram account holds the agent — there is no way around
    that — so the mitigation is being able to sever it immediately. The row is
    kept and stamped rather than deleted: when the link was cut matters more
    than its absence would.
    """
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        text(
            """
            UPDATE telegram_links
            SET revoked_at = now(), updated_at = now()
            WHERE telegram_user_id = :tg AND revoked_at IS NULL
            RETURNING id
            """
        ),
        {"tg": telegram_user_id},
    )
    return result.first() is not None
