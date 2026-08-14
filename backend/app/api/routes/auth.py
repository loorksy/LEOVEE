from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.rate_limit import RateLimitExceeded, enforce_rate_limit
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request, settings: Settings) -> str | None:
    """The client IP for rate-limit keying.

    ``X-Forwarded-For`` is honoured only behind a trusted proxy
    (``TRUST_PROXY_HEADERS``), and then the *rightmost* entry is used — the hop
    our own proxy appended, which a client cannot forge past. Untrusted, the
    header is ignored entirely and the real TCP peer is used, so a direct
    caller cannot mint a fresh rate-limit bucket per request by rotating the
    header.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    if request.client:
        return request.client.host
    return None


@router.post("/signup", response_model=TokenResponse)
async def signup(
    body: SignupRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    ip = _client_ip(request, settings)
    try:
        await enforce_rate_limit(
            key=f"signup:{ip or 'unknown'}",
            limit=settings.auth_rate_limit_signup,
        )
        _, tokens = await auth_service.signup(
            session,
            settings,
            email=body.email,
            password=body.password,
            organization_name=body.organization_name,
            ip_address=ip,
            user_agent=request.headers.get("User-Agent"),
        )
        return tokens
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        ) from exc
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "code": exc.code},
        ) from exc


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    ip = _client_ip(request, settings)
    try:
        await enforce_rate_limit(
            key=f"login:{ip or 'unknown'}:{body.email.lower()}",
            limit=settings.auth_rate_limit_login,
        )
        return await auth_service.login(
            session,
            settings,
            email=body.email,
            password=body.password,
            ip_address=ip,
            user_agent=request.headers.get("User-Agent"),
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        ) from exc
    except AuthError as exc:
        status_code = status.HTTP_401_UNAUTHORIZED
        if exc.code == "email_not_verified":
            status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(
            status_code=status_code,
            detail={"message": str(exc), "code": exc.code},
        ) from exc


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    try:
        return await auth_service.refresh_tokens(
            session,
            settings,
            refresh_token=body.refresh_token,
            ip_address=_client_ip(request, settings),
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": str(exc), "code": exc.code},
        ) from exc


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await auth_service.logout(session, body.refresh_token)
    return MessageResponse(message="Logged out")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    try:
        await auth_service.verify_email(session, body.token)
        return MessageResponse(message="Email verified")
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "code": exc.code},
        ) from exc


@router.post("/password-reset/request", response_model=MessageResponse)
async def password_reset_request(
    body: PasswordResetRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    ip = _client_ip(request, settings)
    try:
        await enforce_rate_limit(
            key=f"pwdreset:{ip or 'unknown'}:{body.email.lower()}",
            limit=settings.auth_rate_limit_password_reset,
        )
        await auth_service.request_password_reset(session, settings, body.email)
        return MessageResponse(message="If the account exists, a reset email was sent")
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        ) from exc


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def password_reset_confirm(
    body: PasswordResetConfirmRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    try:
        await auth_service.confirm_password_reset(session, body.token, body.new_password)
        return MessageResponse(message="Password updated")
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
