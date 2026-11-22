"""Candidate registration, private profiles, opaque login sessions and email proof.

Visitor chat remains free and unrelated to registration. A registered candidate
is NOT a privileged staff user, and email_verified_at stays NULL until proven.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import check_password, hash_password
from app.auth.tokens import digest_token, generate_token
from app.auth.verification import send_verification_email
from app.core.config import Settings, get_settings
from app.core.rate_limit import throttle_client
from app.core.security import utc_aware
from app.db.session import get_db
from app.models.candidate import CandidateEmailToken, CandidateSession, CandidateUser
from app.schemas.candidate import (
    CandidateLogin,
    CandidateOut,
    CandidatePasswordChange,
    CandidateProfilePatch,
    CandidateRegister,
    CandidateTokenOut,
    VerifyEmail,
)

router = APIRouter(prefix="/candidates", tags=["Comptes candidats"])
candidate_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="CandidateBearer",
    description="Candidate token from POST /api/v1/candidates/login; NOT a staff token",
)


def _out(user):
    return CandidateOut.model_validate(
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_active": user.is_active,
            "email_verified_at": user.email_verified_at,
            "education_level": user.education_level,
            "interests": json.loads(user.interests or "[]"),
            "career_goal": user.career_goal,
            "created_at": user.created_at,
        }
    )


@dataclass(frozen=True)
class CandidateIdentity:
    user: CandidateUser
    session: CandidateSession


def require_candidate(
    credentials: HTTPAuthorizationCredentials | None = Security(candidate_bearer),
    db: Session = Depends(get_db),
) -> CandidateIdentity:
    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or expired candidate session",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or len(credentials.credentials) > 200
    ):
        raise unauthorized
    session = db.scalar(
        select(CandidateSession).where(
            CandidateSession.token_hash == digest_token(credentials.credentials)
        )
    )
    if (
        session is None
        or session.revoked_at is not None
        or utc_aware(session.expires_at) <= datetime.now(timezone.utc)
    ):
        raise unauthorized
    user = db.get(CandidateUser, session.user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return CandidateIdentity(user, session)


def _issue_email_challenge(db: Session, user: CandidateUser, settings: Settings):
    if not settings.smtp_host or not settings.smtp_from:
        return False  # No fake verification: account remains unverified until SMTP is configured.
    secret = generate_token()
    db.add(
        CandidateEmailToken(
            user_id=user.id,
            token_hash=digest_token(secret),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
    )
    db.commit()
    try:
        return send_verification_email(user.email, secret, settings)
    except Exception as exc:
        # Do not reveal SMTP credentials/details; retry using authenticated resend endpoint.
        raise HTTPException(
            status_code=503, detail="Verification email delivery unavailable; retry later"
        ) from exc


@router.post(
    "/register",
    response_model=CandidateOut,
    status_code=201,
    summary="Create a candidate account; no registration needed for visitor chat",
)
def register(
    payload: CandidateRegister,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    throttle_client(
        db,
        request,
        settings,
        action="candidate_register",
        limit=settings.candidate_registrations_per_hour,
        period_seconds=3600,
    )
    user = CandidateUser(
        email=str(payload.email).lower(),
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        is_active=True,
        failed_login_count=0,
        interests="[]",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Candidate email already registered") from exc
    db.refresh(user)
    _issue_email_challenge(db, user, settings)
    return _out(user)


@router.post(
    "/login",
    response_model=CandidateTokenOut,
    summary="Login candidate with independent, revocable bearer token",
)
def login(
    payload: CandidateLogin,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    throttle_client(
        db,
        request,
        settings,
        action="candidate_login",
        limit=settings.candidate_login_attempts_per_hour,
        period_seconds=3600,
    )
    now = datetime.now(timezone.utc)
    user = db.scalar(
        select(CandidateUser)
        .where(CandidateUser.email == str(payload.email).lower())
        .with_for_update()
    )
    locked = bool(user and user.locked_until and utc_aware(user.locked_until) > now)
    valid = check_password(
        user.password_hash if user and user.is_active and not locked else None, payload.password
    )
    if user is None or not user.is_active or locked or not valid:
        if user and user.is_active and not locked:
            if user.locked_until and utc_aware(user.locked_until) <= now:
                user.failed_login_count = 0
                user.locked_until = None
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.failed_login_count = 0
                user.locked_until = now + timedelta(minutes=15)
            db.commit()
        raise HTTPException(
            status_code=401,
            detail="Invalid login credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.failed_login_count = 0
    user.locked_until = None
    secret = generate_token()
    expiry = now + timedelta(hours=settings.candidate_session_ttl_hours)
    db.add(CandidateSession(user_id=user.id, token_hash=digest_token(secret), expires_at=expiry))
    db.commit()
    db.refresh(user)
    return CandidateTokenOut(access_token=secret, expires_at=expiry, user=_out(user))


@router.get("/me", response_model=CandidateOut, summary="Read only your own candidate profile")
def me(identity: CandidateIdentity = Depends(require_candidate)):
    return _out(identity.user)


@router.patch("/me", response_model=CandidateOut, summary="Update only your own candidate profile")
def patch_me(
    payload: CandidateProfilePatch,
    identity: CandidateIdentity = Depends(require_candidate),
    db: Session = Depends(get_db),
):
    fields = payload.model_dump(exclude_unset=True)
    if "display_name" in fields and fields["display_name"] is None:
        raise HTTPException(status_code=422, detail="Display name cannot be null")
    for key, value in fields.items():
        if key == "interests":
            value = json.dumps(value or [], ensure_ascii=False)
        setattr(identity.user, key, value)
    db.commit()
    db.refresh(identity.user)
    return _out(identity.user)


@router.post("/logout", status_code=204, summary="Revoke candidate login token")
def logout(identity: CandidateIdentity = Depends(require_candidate), db: Session = Depends(get_db)):
    identity.session.revoked_at = datetime.now(timezone.utc)
    db.commit()


@router.post(
    "/change-password",
    status_code=204,
    summary="Rotate candidate password and revoke all logged-in sessions",
)
def change_password(
    payload: CandidatePasswordChange,
    identity: CandidateIdentity = Depends(require_candidate),
    db: Session = Depends(get_db),
):
    if not check_password(identity.user.password_hash, payload.current_password):
        raise HTTPException(status_code=401, detail="Invalid current password")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="Password must change")
    identity.user.password_hash = hash_password(payload.new_password)
    for session in db.scalars(
        select(CandidateSession).where(
            CandidateSession.user_id == identity.user.id, CandidateSession.revoked_at.is_(None)
        )
    ):
        session.revoked_at = datetime.now(timezone.utc)
    db.commit()


@router.post(
    "/resend-verification",
    status_code=202,
    summary="Email a new proof token (requires configured SMTP)",
)
def resend_verification(
    request: Request,
    identity: CandidateIdentity = Depends(require_candidate),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if identity.user.email_verified_at:
        return {"detail": "Email already verified"}
    throttle_client(
        db,
        request,
        settings,
        action=f"candidate_resend_{identity.user.id}",
        limit=3,
        period_seconds=3600,
    )
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(status_code=503, detail="Email delivery not configured")
    _issue_email_challenge(db, identity.user, settings)
    return {"detail": "If delivery succeeds, a verification email has been sent"}


@router.post(
    "/verify-email",
    status_code=204,
    summary="Prove ownership using the one-time emailed verification token",
)
def verify_email(payload: VerifyEmail, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    claim = db.scalar(
        select(CandidateEmailToken)
        .where(CandidateEmailToken.token_hash == digest_token(payload.token))
        .with_for_update()
    )
    if claim is None or claim.used_at is not None or utc_aware(claim.expires_at) <= now:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    user = db.get(CandidateUser, claim.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    if user.email_verified_at is None:
        user.email_verified_at = now
    for other in db.scalars(
        select(CandidateEmailToken).where(
            CandidateEmailToken.user_id == user.id, CandidateEmailToken.used_at.is_(None)
        )
    ):
        other.used_at = now
    db.commit()


@router.delete(
    "/me",
    status_code=204,
    summary="Permanently delete your candidate account and revoke its sessions",
)
def delete_me(
    identity: CandidateIdentity = Depends(require_candidate), db: Session = Depends(get_db)
):
    db.delete(identity.user)
    db.commit()
