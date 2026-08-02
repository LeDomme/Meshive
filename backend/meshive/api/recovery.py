import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.action_tokens import (
    EMAIL_VERIFICATION,
    PASSWORD_RESET,
    delete_user_action_tokens,
    find_action_token,
    issue_action_token,
)
from meshive.auth.dependencies import get_current_user_allow_password_change
from meshive.auth.passwords import hash_password, verify_password
from meshive.auth.rate_limit import recovery_limiter
from meshive.auth.sessions import utc_now
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.session import UserSession
from meshive.models.user import User
from meshive.models.user_token import UserActionToken
from meshive.repositories.users import (
    get_user_by_recovery_identifier,
    normalize_email,
)
from meshive.schemas.user import (
    ActionMessage,
    ActionTokenRequest,
    EmailChange,
    PasswordRecoveryRequest,
    PasswordReset,
    RecoveryStatus,
    UserRead,
)
from meshive.services.mailer import (
    EmailDeliveryError,
    send_email_verification,
    send_password_reset_email,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["password recovery"])

RECOVERY_ACCEPTED = (
    "If the account is eligible for password recovery, an email has been sent."
)


@router.get("/password-recovery/status", response_model=RecoveryStatus)
def recovery_status(settings: Settings = Depends(get_settings)) -> RecoveryStatus:
    return RecoveryStatus(enabled=settings.email_delivery_enabled)


@router.post(
    "/password-recovery/request",
    response_model=ActionMessage,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordRecoveryRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ActionMessage:
    if not settings.email_delivery_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password recovery email is not configured",
        )
    rate_key = f"password-reset:{payload.identifier.casefold()}"
    _enforce_recovery_rate_limit(rate_key, settings)
    recovery_limiter.record_failure(
        rate_key, window_seconds=settings.auth_rate_limit_window_seconds
    )

    session.execute(
        delete(UserActionToken).where(UserActionToken.expires_at <= utc_now())
    )
    user = get_user_by_recovery_identifier(session, payload.identifier)
    if user is not None and user.is_active and user.email_verified and user.email:
        raw_token = issue_action_token(
            session,
            user,
            purpose=PASSWORD_RESET,
            lifetime=timedelta(minutes=settings.password_reset_lifetime_minutes),
        )
        session.commit()
        background_tasks.add_task(
            _deliver_password_reset, settings, user.email, raw_token
        )
    else:
        session.commit()
    return ActionMessage(message=RECOVERY_ACCEPTED)


@router.post("/password-recovery/reset", response_model=ActionMessage)
def reset_password(
    payload: PasswordReset,
    session: Session = Depends(get_session),
) -> ActionMessage:
    record = find_action_token(session, payload.token, PASSWORD_RESET)
    now = utc_now()
    if record is None or record.expires_at <= now or not record.user.is_active:
        if record is not None:
            session.delete(record)
            session.commit()
        raise _invalid_token_error()
    user = record.user
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different",
        )

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    delete_user_action_tokens(session, user.id)
    session.commit()
    return ActionMessage(
        message="Your password has been reset. You can now sign in."
    )


@router.post("/email", response_model=UserRead)
def change_recovery_email(
    payload: EmailChange,
    user: User = Depends(get_current_user_allow_password_change),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    rate_key = f"current-password:{user.id}"
    _enforce_recovery_rate_limit(rate_key, settings)
    if not verify_password(payload.current_password, user.password_hash):
        recovery_limiter.record_failure(
            rate_key, window_seconds=settings.auth_rate_limit_window_seconds
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect",
        )
    recovery_limiter.clear(rate_key)
    if not settings.email_delivery_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured",
        )

    email = str(payload.email)
    normalized = normalize_email(email)
    if user.normalized_email == normalized and user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already verified",
        )
    _enforce_recovery_rate_limit(f"email-verification:{user.id}", settings)

    delete_user_action_tokens(session, user.id)
    user.email = email
    user.normalized_email = normalized
    user.email_verified_at = None
    raw_token = issue_action_token(
        session,
        user,
        purpose=EMAIL_VERIFICATION,
        lifetime=timedelta(hours=settings.email_verification_lifetime_hours),
        email=email,
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already used by another account",
        ) from error
    _record_verification_attempt(user.id, settings)
    _send_verification_or_error(settings, email, raw_token)
    session.refresh(user)
    return user


@router.post("/email/resend", response_model=ActionMessage)
def resend_email_verification(
    user: User = Depends(get_current_user_allow_password_change),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ActionMessage:
    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No recovery email is configured",
        )
    if user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The recovery email is already verified",
        )
    if not settings.email_delivery_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured",
        )
    _enforce_recovery_rate_limit(f"email-verification:{user.id}", settings)
    raw_token = issue_action_token(
        session,
        user,
        purpose=EMAIL_VERIFICATION,
        lifetime=timedelta(hours=settings.email_verification_lifetime_hours),
        email=user.email,
    )
    session.commit()
    _record_verification_attempt(user.id, settings)
    _send_verification_or_error(settings, user.email, raw_token)
    return ActionMessage(message="A new verification email has been sent.")


@router.post("/email/verify", response_model=ActionMessage)
def verify_recovery_email(
    payload: ActionTokenRequest,
    session: Session = Depends(get_session),
) -> ActionMessage:
    record = find_action_token(session, payload.token, EMAIL_VERIFICATION)
    now = utc_now()
    if (
        record is None
        or record.expires_at <= now
        or not record.user.is_active
        or not record.email
        or not record.user.email
        or record.email != record.user.email
    ):
        if record is not None:
            session.delete(record)
            session.commit()
        raise _invalid_token_error()

    user = record.user
    user.email_verified_at = now
    session.execute(
        delete(UserActionToken).where(
            UserActionToken.user_id == user.id,
            UserActionToken.purpose == EMAIL_VERIFICATION,
        )
    )
    session.commit()
    return ActionMessage(
        message="Your recovery email has been verified successfully."
    )


def _enforce_recovery_rate_limit(key: str, settings: Settings) -> None:
    retry_after = recovery_limiter.retry_after(
        key,
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests; try again later",
            headers={"Retry-After": str(retry_after)},
        )


def _record_verification_attempt(user_id: int, settings: Settings) -> None:
    recovery_limiter.record_failure(
        f"email-verification:{user_id}",
        window_seconds=settings.auth_rate_limit_window_seconds,
    )


def _send_verification_or_error(
    settings: Settings, email: str, raw_token: str
) -> None:
    try:
        send_email_verification(settings, email, raw_token)
    except EmailDeliveryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The verification email could not be delivered",
        ) from error


def _deliver_password_reset(
    settings: Settings, email: str, raw_token: str
) -> None:
    try:
        send_password_reset_email(settings, email, raw_token)
    except EmailDeliveryError:
        logger.exception("Password reset email delivery failed")


def _invalid_token_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The link is invalid or has expired",
    )
