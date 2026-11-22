"""Staff RBAC, fully independent from anonymous visitor tokens."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tokens import digest_token
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.staff import StaffRole, StaffSession, StaffUser

bootstrap_key_scheme = APIKeyHeader(
    name="X-Admin-Key",
    auto_error=False,
    scheme_name="BootstrapKey",
    description="ONE-TIME bootstrap only. This is not a staff login token.",
)
staff_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="StaffBearer",
    description="Opaque token obtained from POST /api/v1/auth/login. Not the visitor token.",
)


def require_bootstrap_key(
    key: str | None = Security(bootstrap_key_scheme),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Bootstrap is not configured")
    if not key or not secrets.compare_digest(key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid bootstrap key")


def utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@dataclass(frozen=True)
class StaffIdentity:
    user: StaffUser
    session: StaffSession


def require_staff(
    credentials: HTTPAuthorizationCredentials | None = Security(staff_bearer_scheme),
    db: Session = Depends(get_db),
) -> StaffIdentity:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired staff session",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or len(credentials.credentials) > 200
    ):
        raise unauthorized
    session = db.scalar(
        select(StaffSession).where(StaffSession.token_hash == digest_token(credentials.credentials))
    )
    if (
        session is None
        or session.revoked_at is not None
        or utc_aware(session.expires_at) <= datetime.now(timezone.utc)
    ):
        raise unauthorized
    user = db.get(StaffUser, session.user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return StaffIdentity(user, session)


def require_roles(*roles: StaffRole) -> Callable:
    role_values = {r.value for r in roles}

    def permission(identity: StaffIdentity = Depends(require_staff)) -> StaffIdentity:
        if identity.user.role not in role_values:
            raise HTTPException(status_code=403, detail="Insufficient staff permissions")
        return identity

    return permission


def require_catalogue_reader(identity: StaffIdentity = Depends(require_staff)) -> StaffIdentity:
    allowed = {
        StaffRole.PLATFORM_ADMIN.value,
        StaffRole.ACADEMIC_IIT.value,
        StaffRole.ACADEMIC_ISB.value,
        StaffRole.DIRECTION.value,
    }
    if identity.user.role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient staff permissions")
    return identity


def require_catalogue_editor(identity: StaffIdentity = Depends(require_staff)) -> StaffIdentity:
    allowed = {
        StaffRole.PLATFORM_ADMIN.value,
        StaffRole.ACADEMIC_IIT.value,
        StaffRole.ACADEMIC_ISB.value,
    }
    if identity.user.role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient staff permissions")
    return identity


def require_same_institution(identity: StaffIdentity, institution_id) -> None:
    if (
        identity.user.role not in {StaffRole.PLATFORM_ADMIN.value, StaffRole.DIRECTION.value}
        and identity.user.institution_id != institution_id
    ):
        # Avoid disclosing whether another institution has a draft.
        raise HTTPException(status_code=404, detail="Programme not found")
