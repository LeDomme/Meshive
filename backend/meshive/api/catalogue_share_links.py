from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from meshive.api.catalog import catalogue_filters, list_models
from meshive.auth.access import get_access_context, require_access_permission
from meshive.auth.catalogue_share_links import (
    TOKEN_PREFIX,
    catalogue_share_link_expiration,
    display_catalogue_share_token_prefix,
    generate_catalogue_share_token,
    hash_catalogue_share_token,
)
from meshive.auth.dependencies import get_current_user
from meshive.auth.passwords import verify_password
from meshive.auth.permissions import CATALOGUE_SHARE_LINKS_MANAGE_OWN, CATALOGUE_VIEW
from meshive.auth.rate_limit import catalogue_share_link_limiter, recovery_limiter
from meshive.auth.sessions import utc_now
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.catalogue_share_link import CatalogueShareLink
from meshive.models.user import User
from meshive.schemas.catalog import CatalogueFilters, ModelPage
from meshive.schemas.catalogue_share_link import (
    CatalogueShareLinkCreate,
    CatalogueShareLinkCreated,
    CatalogueShareLinkRead,
)
from meshive.services.audit import AuditAction, log_event

router = APIRouter(
    prefix="/account/catalogue-share-links",
    tags=["catalogue-share-links"],
)
share_router = APIRouter(prefix="/share/catalogue", tags=["catalogue-share-links"])
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]


def _require_manage_permission(user: User, session: Session) -> None:
    access = get_access_context(session, user)
    require_access_permission(access, CATALOGUE_SHARE_LINKS_MANAGE_OWN)


def _link_read(link: CatalogueShareLink) -> CatalogueShareLinkRead:
    return CatalogueShareLinkRead(
        id=link.id,
        name=link.name,
        token_prefix=link.token_prefix,
        created_at=link.created_at,
        expires_at=link.expires_at,
        last_used_at=link.last_used_at,
        status="expired" if link.expires_at <= utc_now() else "active",
    )


@router.get("", response_model=list[CatalogueShareLinkRead])
def list_catalogue_share_links(
    user: CurrentUser, session: SessionDependency
) -> list[CatalogueShareLinkRead]:
    _require_manage_permission(user, session)
    links = session.scalars(
        select(CatalogueShareLink)
        .where(CatalogueShareLink.user_id == user.id)
        .order_by(CatalogueShareLink.created_at.desc(), CatalogueShareLink.id.desc())
    )
    return [_link_read(link) for link in links]


@router.post("", response_model=CatalogueShareLinkCreated, status_code=status.HTTP_201_CREATED)
def create_catalogue_share_link(
    payload: CatalogueShareLinkCreate,
    user: CurrentUser,
    session: SessionDependency,
    settings: Settings = Depends(get_settings),
) -> CatalogueShareLinkCreated:
    _require_manage_permission(user, session)
    rate_limit_key = f"catalogue-share-link-password:{user.id}"
    retry_after = recovery_limiter.retry_after(
        rate_limit_key,
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(retry_after)}
        )
    if not verify_password(payload.current_password, user.password_hash):
        recovery_limiter.record_failure(
            rate_limit_key, window_seconds=settings.auth_rate_limit_window_seconds
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    recovery_limiter.clear(rate_limit_key)
    token = generate_catalogue_share_token()
    link = CatalogueShareLink(
        user_id=user.id,
        name=payload.name,
        token_hash=hash_catalogue_share_token(token),
        token_prefix=display_catalogue_share_token_prefix(token),
        expires_at=catalogue_share_link_expiration(payload.expires_in_seconds),
    )
    session.add(link)
    session.flush()
    log_event(
        session,
        user,
        AuditAction.CATALOGUE_SHARE_LINK_CREATED,
        "catalogue_share_link",
        link.name,
        target_id=link.id,
        details={"token_prefix": link.token_prefix, "expires_at": link.expires_at.isoformat()},
    )
    session.commit()
    session.refresh(link)
    return CatalogueShareLinkCreated(**_link_read(link).model_dump(), token=token)


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_catalogue_share_link(
    link_id: int, user: CurrentUser, session: SessionDependency
) -> Response:
    _require_manage_permission(user, session)
    link = session.scalar(
        select(CatalogueShareLink).where(
            CatalogueShareLink.id == link_id, CatalogueShareLink.user_id == user.id
        )
    )
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Catalogue share link not found"
        )
    log_event(
        session,
        user,
        AuditAction.CATALOGUE_SHARE_LINK_REVOKED,
        "catalogue_share_link",
        link.name,
        target_id=link.id,
        details={"token_prefix": link.token_prefix, "expires_at": link.expires_at.isoformat()},
    )
    session.delete(link)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Catalogue share link not found"
    )


def _share_owner(token: str, session: Session) -> tuple[CatalogueShareLink, User]:
    if not token.startswith(TOKEN_PREFIX):
        raise _not_found()
    link = session.scalar(
        select(CatalogueShareLink).where(
            CatalogueShareLink.token_hash == hash_catalogue_share_token(token)
        )
    )
    if link is None or link.expires_at <= utc_now():
        raise _not_found()
    owner = session.get(User, link.user_id)
    if owner is None or not owner.is_active or owner.must_change_password:
        raise _not_found()
    access = get_access_context(session, owner)
    require_access_permission(access, CATALOGUE_VIEW)
    retry_after = catalogue_share_link_limiter.check_and_record(
        str(link.id), limit=120, window_seconds=60
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(retry_after)}
        )
    if link.last_used_at is None or link.last_used_at <= utc_now() - timedelta(minutes=15):
        link.last_used_at = utc_now()
        try:
            session.commit()
        except OperationalError:
            session.rollback()
    return link, owner


def _share_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Referrer-Policy"] = "no-referrer"


@share_router.get("/{token}/models", response_model=ModelPage)
def share_models(
    token: str,
    response: Response,
    session: SessionDependency,
    search: str | None = Query(default=None, max_length=200),
    model_name: str | None = Query(default=None, alias="model", max_length=255),
    creator: str | None = Query(default=None, max_length=255),
    creator_profile_id: int | None = Query(default=None, ge=1),
    franchise: str | None = Query(default=None, max_length=255),
    series: str | None = Query(default=None, max_length=255),
    collection: str | None = Query(default=None, max_length=255),
    variant: str | None = Query(default=None, max_length=255),
    tag_id: int | None = None,
    source_id: int | None = None,
    model_status: str | None = Query(default=None, alias="status", max_length=30),
    sort: Literal[
        "meshive_newest",
        "meshive_oldest",
        "files_newest",
        "files_oldest",
        "name_asc",
        "name_desc",
        "creator_asc",
        "creator_desc",
    ] = "name_asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=48, ge=1, le=100),
) -> ModelPage:
    _, owner = _share_owner(token, session)
    result = list_models(
        search,
        model_name,
        creator,
        creator_profile_id,
        franchise,
        series,
        collection,
        variant,
        tag_id,
        source_id,
        model_status,
        sort,
        page,
        page_size,
        owner,
        session,
    )
    for item in result.items:
        item.thumbnail_url = None
    _share_response(response)
    return result


@share_router.get("/{token}/filters", response_model=CatalogueFilters)
def share_filters(
    token: str,
    response: Response,
    session: SessionDependency,
    search: str | None = Query(default=None, max_length=200),
    model_name: str | None = Query(default=None, alias="model", max_length=255),
    creator: str | None = Query(default=None, max_length=255),
    creator_profile_id: int | None = Query(default=None, ge=1),
    franchise: str | None = Query(default=None, max_length=255),
    series: str | None = Query(default=None, max_length=255),
    collection: str | None = Query(default=None, max_length=255),
    variant: str | None = Query(default=None, max_length=255),
    tag_id: int | None = None,
    source_id: int | None = None,
    model_status: str | None = Query(default=None, alias="status", max_length=30),
) -> CatalogueFilters:
    _, owner = _share_owner(token, session)
    result = catalogue_filters(
        search,
        model_name,
        creator,
        creator_profile_id,
        franchise,
        series,
        collection,
        variant,
        tag_id,
        source_id,
        model_status,
        owner,
        session,
    )
    _share_response(response)
    return result
