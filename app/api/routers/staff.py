"""Platform admin provisioned staff; there is intentionally no public signup."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routers.auth import _create_user
from app.core.security import StaffIdentity, require_roles
from app.db.session import get_db
from app.models import Institution
from app.models.staff import StaffRole, StaffSession, StaffUser
from app.schemas.staff import StaffCreate, StaffOut, StaffUpdate

router = APIRouter(prefix="/staff", tags=["Administration des comptes"])


def check_role_institution(db: Session, role: StaffRole, institution_id: uuid.UUID | None) -> None:
    expected = {StaffRole.ACADEMIC_IIT: "IIT", StaffRole.ACADEMIC_ISB: "ISB"}
    if role in expected:
        institution = db.get(Institution, institution_id) if institution_id else None
        if institution is None or institution.code != expected[role]:
            raise HTTPException(status_code=422, detail=f"Role requires {expected[role]} institution ID")
    elif institution_id is not None:
        raise HTTPException(status_code=422, detail="This role cannot be institution-scoped")

admin_only = require_roles(StaffRole.PLATFORM_ADMIN)


@router.get("", response_model=list[StaffOut], summary="List staff users (platform admin)")
def list_staff(
    identity: StaffIdentity = Depends(admin_only),
    db: Session = Depends(get_db),
) -> list[StaffUser]:
    return list(db.scalars(select(StaffUser).order_by(StaffUser.email).limit(200)))


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED, summary="Provision a staff user")
def create_staff(
    payload: StaffCreate,
    identity: StaffIdentity = Depends(admin_only),
    db: Session = Depends(get_db),
) -> StaffUser:
    check_role_institution(db, payload.role, payload.institution_id)
    return _create_user(db, payload)


@router.post("/{user_id}/deactivate", response_model=StaffOut, summary="Deactivate staff and revoke all tokens")
def deactivate_staff(
    user_id: uuid.UUID,
    identity: StaffIdentity = Depends(admin_only),
    db: Session = Depends(get_db),
) -> StaffUser:
    if user_id == identity.user.id:
        raise HTTPException(status_code=409, detail="Cannot deactivate your own administrator account")
    user = db.get(StaffUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Staff user not found")
    user.is_active = False
    now = datetime.now(timezone.utc)
    for session in db.scalars(select(StaffSession).where(StaffSession.user_id == user.id, StaffSession.revoked_at.is_(None))):
        session.revoked_at = now
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=StaffOut, summary="Edit staff name, role and institution scope")
def update_staff(
    user_id: uuid.UUID,
    payload: StaffUpdate,
    identity: StaffIdentity = Depends(admin_only),
    db: Session = Depends(get_db),
) -> StaffUser:
    user = db.get(StaffUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Staff user not found")
    changes = payload.model_fields_set
    if ("display_name" in changes and payload.display_name is None) or ("role" in changes and payload.role is None):
        raise HTTPException(status_code=422, detail="Role or name cannot be null")
    role = payload.role if "role" in changes else StaffRole(user.role)
    institution_id = payload.institution_id if "institution_id" in changes else user.institution_id
    check_role_institution(db, role, institution_id)
    if user.id == identity.user.id and role != StaffRole.PLATFORM_ADMIN:
        raise HTTPException(status_code=409, detail="Cannot demote your own administrator account")
    changed_permissions = role.value != user.role or institution_id != user.institution_id
    if "display_name" in changes:
        user.display_name = payload.display_name
    user.role = role.value
    user.institution_id = institution_id
    # Revoke all existing sessions on any permission change: no stale elevated tokens.
    if changed_permissions:
        now = datetime.now(timezone.utc)
        for session in db.scalars(select(StaffSession).where(StaffSession.user_id == user.id, StaffSession.revoked_at.is_(None))):
            session.revoked_at = now
    db.commit()
    db.refresh(user)
    return user
