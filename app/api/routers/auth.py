"""Account bootstrap, login, logout and password rotation."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import check_password, hash_password
from app.auth.tokens import digest_token, generate_token
from app.core.config import Settings, get_settings
from app.core.security import StaffIdentity, require_bootstrap_key, require_staff, utc_aware
from app.db.session import get_db
from app.models.staff import StaffRole, StaffSession, StaffUser
from app.schemas.staff import PasswordChange, StaffCreate, StaffLogin, StaffOut, StaffTokenOut

router = APIRouter(prefix="/auth", tags=["Authentification staff"])


def normalize_email(value: str) -> str:
    return value.strip().lower()


def _create_user(db: Session, payload: StaffCreate) -> StaffUser:
    user = StaffUser(
        email=normalize_email(str(payload.email)), display_name=payload.display_name,
        password_hash=hash_password(payload.password), role=payload.role.value,
        institution_id=payload.institution_id, is_active=True, failed_login_count=0,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Staff email already exists") from exc
    db.refresh(user)
    return user


@router.post(
    "/bootstrap", response_model=StaffOut, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_bootstrap_key)],
    summary="Create FIRST platform administrator once (requires bootstrap key)",
)
def bootstrap_first_admin(payload: StaffCreate, db: Session = Depends(get_db)) -> StaffUser:
    if payload.role != StaffRole.PLATFORM_ADMIN or payload.institution_id is not None:
        raise HTTPException(status_code=422, detail="First user must be an unscoped platform administrator")
    # PostgreSQL advisory transaction lock serializes concurrent first-admin requests.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(9023011703)"))
    if db.scalar(select(StaffUser.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="Bootstrap already completed")
    return _create_user(db, payload)


@router.post("/login", response_model=StaffTokenOut, summary="Login and get an expiring staff bearer token")
def login(
    payload: StaffLogin,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StaffTokenOut:
    now = datetime.now(timezone.utc)
    # Row lock also makes lockout counters safe with concurrent logins in PostgreSQL.
    user = db.scalar(
        select(StaffUser).where(StaffUser.email == normalize_email(str(payload.email))).with_for_update()
    )
    locked = bool(user and user.locked_until and utc_aware(user.locked_until) > now)
    valid = check_password(user.password_hash if user and user.is_active and not locked else None, payload.password)
    if user is None or not user.is_active or locked or not valid:
        if user and user.is_active and not locked:
            if user.locked_until and utc_aware(user.locked_until) <= now:
                user.failed_login_count = 0
                user.locked_until = None
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(
            status_code=401, detail="Invalid login credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.failed_login_count = 0
    user.locked_until = None
    expires_at = now + timedelta(hours=settings.staff_session_ttl_hours)
    secret = generate_token()
    db.add(StaffSession(user_id=user.id, token_hash=digest_token(secret), expires_at=expires_at))
    db.commit()
    db.refresh(user)
    return StaffTokenOut(access_token=secret, expires_at=expires_at, user=StaffOut.model_validate(user))


@router.get("/me", response_model=StaffOut, summary="View authenticated staff profile")
def me(identity: StaffIdentity = Depends(require_staff)) -> StaffUser:
    return identity.user


@router.post("/logout", status_code=204, summary="Revoke current staff login token")
def logout(identity: StaffIdentity = Depends(require_staff), db: Session = Depends(get_db)) -> None:
    identity.session.revoked_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/change-password", status_code=204, summary="Change password and revoke all active sessions")
def change_password(
    payload: PasswordChange,
    identity: StaffIdentity = Depends(require_staff),
    db: Session = Depends(get_db),
) -> None:
    if not check_password(identity.user.password_hash, payload.current_password):
        raise HTTPException(status_code=401, detail="Invalid current password")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="New password must differ from the old password")
    identity.user.password_hash = hash_password(payload.new_password)
    for active in db.scalars(select(StaffSession).where(StaffSession.user_id == identity.user.id, StaffSession.revoked_at.is_(None))):
        active.revoked_at = datetime.now(timezone.utc)
    db.commit()
