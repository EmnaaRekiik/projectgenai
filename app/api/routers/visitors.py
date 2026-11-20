"""SA-25/SA-26: secure anonymous sessions and persistent, bounded history."""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import throttle_client
from app.db.session import get_db
from app.models.visitor import ConversationMessage, VisitorSession
from app.schemas.visitor import (
    ContextMessage,
    ConversationContext,
    MessageOut,
    MessagePage,
    UserMessageCreate,
    VisitorSessionCreated,
    VisitorSessionOut,
)

router = APIRouter(prefix="/visitor/sessions", tags=["Sessions visiteurs et mémoire"])
visitor_token_scheme = APIKeyHeader(
    name="X-Visitor-Token",
    scheme_name="VisitorSessionToken",
    auto_error=False,
    description="Session token returned by POST /visitor/sessions. Never share or log this token.",
)


def _utc(dt: datetime) -> datetime:
    """SQLite unit tests do not retain tzinfo; PostgreSQL does."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _owned_active_session(
    session_id: uuid.UUID,
    db: Session,
    token: str | None,
    *,
    for_update: bool = False,
) -> VisitorSession:
    if not token:
        raise HTTPException(status_code=401, detail="Missing visitor token")
    statement = select(VisitorSession).where(VisitorSession.id == session_id)
    if for_update:
        # Locks the session row on PostgreSQL so concurrent writes get distinct sequences.
        statement = statement.with_for_update()
    record = db.scalar(statement)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if record is None or not hmac.compare_digest(record.token_hash, token_hash):
        # Do not reveal whether another visitor's session exists.
        raise HTTPException(status_code=404, detail="Session not found")
    if _utc(record.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Session expired")
    return record


@router.post("", response_model=VisitorSessionCreated, status_code=status.HTTP_201_CREATED,
             summary="Create an anonymous session and receive a one-time access token")
def create_session(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VisitorSessionCreated:
    throttle_client(db, request, settings, action="visitor_create",
                    limit=settings.visitor_creations_per_hour, period_seconds=3600)
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    record = VisitorSession(
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=now + timedelta(hours=settings.visitor_session_ttl_hours),
        last_activity_at=now,
        next_message_sequence=1,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return VisitorSessionCreated(
        **VisitorSessionOut.model_validate(record).model_dump(), token=token
    )


@router.get("/{session_id}", response_model=VisitorSessionOut, summary="Read your session metadata")
def get_session(
    session_id: uuid.UUID,
    token: str | None = Security(visitor_token_scheme),
    db: Session = Depends(get_db),
) -> VisitorSession:
    return _owned_active_session(session_id, db, token)


@router.post("/{session_id}/messages", response_model=MessageOut,
             status_code=status.HTTP_201_CREATED,
             summary="Append a user message to a visitor's conversation")
def add_user_message(
    session_id: uuid.UUID,
    payload: UserMessageCreate,
    token: str | None = Security(visitor_token_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ConversationMessage:
    record = _owned_active_session(session_id, db, token, for_update=True)
    if record.chat_lease_until is not None and _utc(record.chat_lease_until) > datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Chat response in progress; retry later")
    if record.next_message_sequence > settings.visitor_max_messages:
        raise HTTPException(
            status_code=409, detail="Session message limit reached; start a new session"
        )
    now = datetime.now(timezone.utc)
    message = ConversationMessage(
        session_id=record.id,
        role="user",
        sequence=record.next_message_sequence,
        content=payload.content,
    )
    record.next_message_sequence += 1
    record.last_activity_at = now
    db.add(message)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrent message conflict; retry") from exc
    db.refresh(message)
    return message


@router.get("/{session_id}/messages", response_model=MessagePage,
            summary="Paginate your conversation messages")
def list_messages(
    session_id: uuid.UUID,
    token: str | None = Security(visitor_token_scheme),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> MessagePage:
    _owned_active_session(session_id, db, token)
    criterion = ConversationMessage.session_id == session_id
    total = db.scalar(select(func.count()).select_from(ConversationMessage).where(criterion)) or 0
    records = db.scalars(
        select(ConversationMessage).where(criterion)
        .order_by(ConversationMessage.sequence.asc()).limit(limit).offset(offset)
    ).all()
    return MessagePage(items=[MessageOut.model_validate(item) for item in records],
                       total=total, limit=limit, offset=offset)


@router.get("/{session_id}/context", response_model=ConversationContext,
            summary="Retrieve the latest context window for later LLM integration")
def get_context(
    session_id: uuid.UUID,
    token: str | None = Security(visitor_token_scheme),
    limit: int = Query(default=12, ge=1, le=30),
    db: Session = Depends(get_db),
) -> ConversationContext:
    _owned_active_session(session_id, db, token)
    # Obtain the last N+1 messages without loading the entire transcript.
    recent = list(db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.sequence.desc()).limit(limit + 1)
    ))
    truncated = len(recent) > limit
    records = reversed(recent[:limit])
    return ConversationContext(
        session_id=session_id,
        messages=[ContextMessage(sequence=item.sequence, role=item.role, content=item.content)
                  for item in records],
        truncated=truncated,
    )


@router.delete("/{session_id}", status_code=204,
               summary="Permanently delete your visitor session and its messages")
def delete_session(
    session_id: uuid.UUID,
    token: str | None = Security(visitor_token_scheme),
    db: Session = Depends(get_db),
) -> Response:
    record = _owned_active_session(session_id, db, token)
    db.delete(record)
    db.commit()
    return Response(status_code=204)
