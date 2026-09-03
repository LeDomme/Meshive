from sqlalchemy.orm import Session

from meshive.auth.access import get_access_context
from meshive.models.user import User
from meshive.schemas.user import CurrentUserRead, RoleDefinitionRead, SourceAccessRead


def build_current_user_response(user: User, session: Session) -> CurrentUserRead:
    """Build the complete access-aware response for the authenticated user."""
    access = get_access_context(session, user)
    role = user.role_definition
    return CurrentUserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        email_verified=user.email_verified,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        role_definition=(
            RoleDefinitionRead(
                id=role.id,
                name=role.name,
                is_system=role.is_system,
                is_superuser=role.is_superuser,
            )
            if role is not None
            else None
        ),
        permissions=sorted(access.permission_keys),
        source_access=SourceAccessRead(
            all_sources=access.all_sources,
            source_ids=sorted(access.source_ids),
        ),
    )
