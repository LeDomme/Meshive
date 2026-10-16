from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.auth.access import require_permission
from meshive.auth.api_tokens import (
    api_token_expiration,
    display_api_token_prefix,
    generate_api_token,
    hash_api_token,
)
from meshive.auth.dependencies import get_current_user
from meshive.auth.passwords import verify_password
from meshive.auth.permissions import API_TOKENS_MANAGE_OWN
from meshive.auth.rate_limit import recovery_limiter
from meshive.auth.sessions import utc_now
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.api_token import ApiToken
from meshive.models.user import User
from meshive.schemas.api_token import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from meshive.services.audit import AuditAction, log_event

router = APIRouter(
    prefix="/account/tokens",
    tags=["api-tokens"],
    dependencies=[Depends(require_permission(API_TOKENS_MANAGE_OWN))],
)

CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]


def _token_read(token: ApiToken) -> ApiTokenRead:
    expired = token.expires_at is not None and token.expires_at <= utc_now()
    return ApiTokenRead(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        status="expired" if expired else "active",
    )


@router.get("", response_model=list[ApiTokenRead])
def list_api_tokens(user: CurrentUser, session: SessionDependency) -> list[ApiTokenRead]:
    tokens = session.scalars(
        select(ApiToken)
        .where(ApiToken.user_id == user.id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    )
    return [_token_read(token) for token in tokens]


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
def create_api_token(
    payload: ApiTokenCreate,
    user: CurrentUser,
    session: SessionDependency,
    settings: Settings = Depends(get_settings),
) -> ApiTokenCreated:
    rate_limit_key = f"api-token-password:{user.id}"
    retry_after = recovery_limiter.retry_after(
        rate_limit_key,
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many password attempts; try again later",
            headers={"Retry-After": str(retry_after)},
        )
    if not verify_password(payload.current_password, user.password_hash):
        recovery_limiter.record_failure(
            rate_limit_key,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect",
        )
    recovery_limiter.clear(rate_limit_key)

    plaintext = generate_api_token()
    token = ApiToken(
        user_id=user.id,
        name=payload.name,
        token_hash=hash_api_token(plaintext),
        token_prefix=display_api_token_prefix(plaintext),
        expires_at=api_token_expiration(payload.expires_in_seconds),
    )
    session.add(token)
    session.flush()
    log_event(
        session,
        user,
        AuditAction.API_TOKEN_CREATED,
        "api_token",
        token.name,
        target_id=token.id,
        details={
            "token_prefix": token.token_prefix,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        },
    )
    session.commit()
    session.refresh(token)

    metadata = _token_read(token)
    return ApiTokenCreated(**metadata.model_dump(), token=plaintext)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_token(
    token_id: int,
    user: CurrentUser,
    session: SessionDependency,
) -> None:
    token = session.scalar(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
    )
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API token not found")

    log_event(
        session,
        user,
        AuditAction.API_TOKEN_REVOKED,
        "api_token",
        token.name,
        target_id=token.id,
        details={
            "token_prefix": token.token_prefix,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        },
    )
    session.delete(token)
    session.commit()
