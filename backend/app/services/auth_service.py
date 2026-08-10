import re
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.datetime_utils import ensure_utc, utc_now
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.auth_token import AuthToken, AuthTokenPurpose
from app.models.base import OrganizationMemberRole, OrganizationStatus, UserStatus
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.session import Session
from app.models.user import User
from app.providers.email.base import EmailMessage
from app.providers.email.factory import get_email_provider
from app.schemas.auth import TokenResponse


class AuthError(Exception):
    def __init__(self, message: str, code: str = "auth_error") -> None:
        super().__init__(message)
        self.code = code


def _slugify(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean[:48] or "org"


async def _unique_org_slug(session: AsyncSession, base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    suffix = 0
    while True:
        existing = await session.scalar(
            select(Organization.id).where(Organization.slug == candidate)
        )
        if existing is None:
            return candidate
        suffix += 1
        candidate = f"{slug}-{suffix}"


async def signup(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    organization_name: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[User, TokenResponse]:
    normalized = email.strip().lower()
    existing = await session.scalar(select(User.id).where(User.email == normalized))
    if existing is not None:
        raise AuthError("Email already registered", "email_taken")

    org_name = organization_name or f"{normalized.split('@')[0].title()}'s Organization"
    org = Organization(
        name=org_name,
        slug=await _unique_org_slug(session, normalized.split("@")[0]),
        status=OrganizationStatus.ACTIVE,
    )
    user = User(
        email=normalized,
        password_hash=hash_password(password),
        status=UserStatus.PENDING_VERIFICATION,
    )
    session.add_all([org, user])
    await session.flush()

    session.add(
        OrganizationMember(
            tenant_id=org.id,
            user_id=user.id,
            role=OrganizationMemberRole.ORG_OWNER,
        )
    )

    verify_token = generate_opaque_token()
    session.add(
        AuthToken(
            user_id=user.id,
            token_hash=hash_token(verify_token),
            purpose=AuthTokenPurpose.EMAIL_VERIFY,
            expires_at=utc_now() + timedelta(hours=24),
        )
    )
    await session.flush()

    verify_url = f"{settings.public_url}/verify-email?token={verify_token}"
    await get_email_provider().send(
        EmailMessage(
            to=normalized,
            subject="Verify your Leovee email",
            html_body=f'<p>Welcome to Leovee.</p><p><a href="{verify_url}">Verify email</a></p>',
            text_body=f"Verify your email: {verify_url}",
        )
    )

    token_response = await _create_session_tokens(
        session,
        settings,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return user, token_response


async def verify_email(session: AsyncSession, token: str) -> None:
    token_hash = hash_token(token)
    row = await session.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == AuthTokenPurpose.EMAIL_VERIFY,
            AuthToken.used_at.is_(None),
        )
    )
    if row is None or ensure_utc(row.expires_at) < utc_now():
        raise AuthError("Invalid or expired verification token", "invalid_token")

    user = await session.get(User, row.user_id)
    if user is None:
        raise AuthError("User not found", "user_not_found")

    user.email_verified_at = utc_now()
    user.status = UserStatus.ACTIVE
    row.used_at = utc_now()


async def login(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenResponse:
    normalized = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == normalized))
    if user is None or user.password_hash is None:
        raise AuthError("Invalid email or password", "invalid_credentials")
    if not verify_password(user.password_hash, password):
        raise AuthError("Invalid email or password", "invalid_credentials")
    if user.status == UserStatus.SUSPENDED:
        raise AuthError("Account suspended", "account_suspended")
    if user.email_verified_at is None:
        raise AuthError("Email not verified", "email_not_verified")

    user.last_login_at = utc_now()
    return await _create_session_tokens(
        session,
        settings,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def refresh_tokens(
    session: AsyncSession,
    settings: Settings,
    *,
    refresh_token: str,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenResponse:
    token_hash = hash_token(refresh_token)
    db_session = await session.scalar(
        select(Session).where(
            Session.refresh_token_hash == token_hash,
            Session.revoked_at.is_(None),
        )
    )
    if db_session is None or ensure_utc(db_session.expires_at) < utc_now():
        raise AuthError("Invalid or expired refresh token", "invalid_refresh")

    db_session.revoked_at = utc_now()
    user = await session.get(User, db_session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthError("Account unavailable", "account_unavailable")

    return await _create_session_tokens(
        session,
        settings,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def logout(session: AsyncSession, refresh_token: str) -> None:
    token_hash = hash_token(refresh_token)
    db_session = await session.scalar(
        select(Session).where(
            Session.refresh_token_hash == token_hash,
            Session.revoked_at.is_(None),
        )
    )
    if db_session is not None:
        db_session.revoked_at = utc_now()


async def request_password_reset(session: AsyncSession, settings: Settings, email: str) -> None:
    normalized = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == normalized))
    if user is None:
        return

    reset_token = generate_opaque_token()
    session.add(
        AuthToken(
            user_id=user.id,
            token_hash=hash_token(reset_token),
            purpose=AuthTokenPurpose.PASSWORD_RESET,
            expires_at=utc_now() + timedelta(hours=1),
        )
    )
    reset_url = f"{settings.public_url}/reset-password?token={reset_token}"
    await get_email_provider().send(
        EmailMessage(
            to=normalized,
            subject="Reset your Leovee password",
            html_body=f'<p><a href="{reset_url}">Reset password</a></p>',
            text_body=f"Reset password: {reset_url}",
        )
    )


async def confirm_password_reset(session: AsyncSession, token: str, new_password: str) -> None:
    token_hash = hash_token(token)
    row = await session.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == AuthTokenPurpose.PASSWORD_RESET,
            AuthToken.used_at.is_(None),
        )
    )
    if row is None or ensure_utc(row.expires_at) < utc_now():
        raise AuthError("Invalid or expired reset token", "invalid_token")

    user = await session.get(User, row.user_id)
    if user is None:
        raise AuthError("User not found", "user_not_found")

    user.password_hash = hash_password(new_password)
    row.used_at = utc_now()


async def get_user_for_access_token(
    session: AsyncSession,
    settings: Settings,
    access_token: str,
) -> tuple[User, Session]:
    from app.core.security import decode_access_token

    try:
        claims = decode_access_token(settings, access_token)
    except Exception as exc:
        raise AuthError("Invalid access token", "invalid_token") from exc

    session_id = uuid.UUID(claims["sid"])
    user_id = uuid.UUID(claims["sub"])
    db_session = await session.get(Session, session_id)
    if (
        db_session is None
        or db_session.user_id != user_id
        or db_session.revoked_at is not None
        or ensure_utc(db_session.expires_at) < utc_now()
    ):
        raise AuthError("Session expired or revoked", "session_revoked")

    user = await session.get(User, user_id)
    if user is None:
        raise AuthError("Account unavailable", "account_unavailable")
    if user.email_verified_at is None:
        raise AuthError("Email not verified", "email_not_verified")
    if user.status != UserStatus.ACTIVE:
        raise AuthError("Account unavailable", "account_unavailable")
    return user, db_session


async def _create_session_tokens(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenResponse:
    refresh_token = generate_opaque_token()
    expires_at = utc_now() + timedelta(days=settings.refresh_token_expire_days)
    db_session = Session(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    session.add(db_session)
    await session.flush()

    access_token, expires_in = create_access_token(
        settings=settings,
        user_id=str(user.id),
        session_id=str(db_session.id),
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
