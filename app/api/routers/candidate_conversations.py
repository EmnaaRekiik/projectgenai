"""T9: keep a visitor's conversation after the candidate logs in or creates an account.

Rules (docs/DONNEES_T4_T5.md):
- two proofs are required: the candidate Bearer token AND the visitor token of the session being claimed;
- explicit consent (``consent: true``), otherwise 422;
- visitor token fingerprint compared in constant time; wrong visitor token -> 403, unknown session -> 404,
  expired session -> 410;
- one visitor session can only be claimed once (unique ``source_visitor_session_id``): another candidate gets 409,
  the same candidate repeating the call gets the existing conversation (idempotent, ``already_claimed``);
- messages are COPIED in one transaction. The visitor tables are not modified and still expire normally.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Security
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routers.candidates import CandidateIdentity, require_candidate
from app.api.routers.visitors import visitor_token_scheme
from app.core.config import Settings, get_settings
from app.core.rate_limit import throttle_client
from app.core.security import utc_aware
from app.db.session import get_db
from app.models.candidate_data import CandidateConversation, CandidateMessage
from app.models.visitor import ConversationMessage, VisitorSession
from app.schemas.candidate_conversation import (
    ClaimOut,
    ClaimRequest,
    ConversationMessageOut,
    ConversationMessagePage,
    ConversationOut,
)

router = APIRouter(prefix="/candidates/me/conversations", tags=["Conversations du candidat"])

TITLE_MAX = 180
CLAIM_ATTEMPTS_PER_HOUR = 30  # slows down guessing of visitor session ids and tokens


def _count(db: Session, conversation_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(CandidateMessage)
            .where(CandidateMessage.conversation_id == conversation_id)
        )
        or 0
    )


def _out(db: Session, conversation: CandidateConversation, cls=ConversationOut, **extra):
    data = ConversationOut.model_validate(conversation).model_dump()
    data["message_count"] = _count(db, conversation.id)
    return cls(**data, **extra)


def _owned(
    db: Session, identity: CandidateIdentity, conversation_id: uuid.UUID
) -> CandidateConversation:
    conversation = db.get(CandidateConversation, conversation_id)
    # Same answer for "does not exist" and "belongs to someone else".
    if conversation is None or conversation.candidate_id != identity.user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _title_from(messages: list[ConversationMessage]) -> str | None:
    for message in messages:
        if message.role == "user":
            text = " ".join(message.content.split())
            return text[:TITLE_MAX] if text else None
    return None


@router.post(
    "/claim",
    response_model=ClaimOut,
    status_code=201,
    summary="Attach a visitor conversation to your account (explicit consent required)",
    responses={
        200: {"description": "Same candidate repeated the claim: existing conversation returned"},
        403: {"description": "Visitor token does not match this session"},
        404: {"description": "Visitor session not found (or already purged)"},
        409: {
            "description": "Session already attached to another account, empty, or chat in progress"
        },
        410: {"description": "Visitor session expired"},
    },
)
def claim_visitor_conversation(
    payload: ClaimRequest,
    request: Request,
    response: Response,
    identity: CandidateIdentity = Depends(require_candidate),
    visitor_token: str | None = Security(visitor_token_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ClaimOut:
    throttle_client(
        db,
        request,
        settings,
        action=f"candidate_claim_{identity.user.id}",
        limit=CLAIM_ATTEMPTS_PER_HOUR,
        period_seconds=3600,
    )
    if not visitor_token:
        raise HTTPException(status_code=401, detail="Missing visitor token")
    # Lock the visitor session so a double click or two devices cannot copy twice.
    visitor = db.scalar(
        select(VisitorSession)
        .where(VisitorSession.id == payload.visitor_session_id)
        .with_for_update()
    )
    if visitor is None:
        existing = db.scalar(
            select(CandidateConversation).where(
                CandidateConversation.source_visitor_session_id == payload.visitor_session_id,
                CandidateConversation.candidate_id == identity.user.id,
            )
        )
        if existing is not None:
            # The visitor session was purged after a successful claim: the repeat call still succeeds.
            response.status_code = 200
            return _out(db, existing, ClaimOut, already_claimed=True)
        raise HTTPException(status_code=404, detail="Visitor session not found")
    supplied = hashlib.sha256(visitor_token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(visitor.token_hash, supplied):
        raise HTTPException(status_code=403, detail="This visitor session is not yours")
    now = datetime.now(timezone.utc)
    if utc_aware(visitor.expires_at) <= now:
        raise HTTPException(status_code=410, detail="Visitor session expired")

    existing = db.scalar(
        select(CandidateConversation).where(
            CandidateConversation.source_visitor_session_id == visitor.id
        )
    )
    if existing is not None:
        if existing.candidate_id == identity.user.id:
            response.status_code = 200
            return _out(db, existing, ClaimOut, already_claimed=True)
        raise HTTPException(
            status_code=409, detail="This visitor conversation is already attached to an account"
        )

    if visitor.chat_lease_until is not None and utc_aware(visitor.chat_lease_until) > now:
        raise HTTPException(status_code=409, detail="Chat response in progress; retry in a moment")
    messages = list(
        db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == visitor.id)
            .order_by(ConversationMessage.sequence.asc())
        )
    )
    if not messages:
        raise HTTPException(
            status_code=409, detail="This visitor session has no messages to attach"
        )

    conversation = CandidateConversation(
        candidate_id=identity.user.id,
        source_visitor_session_id=visitor.id,
        consent_given_at=now,
        claimed_at=now,
        title=_title_from(messages),
        status="ACTIVE",
        next_message_sequence=messages[-1].sequence + 1,
    )
    db.add(conversation)
    db.flush()
    for message in messages:
        db.add(
            CandidateMessage(
                conversation_id=conversation.id,
                sequence=message.sequence,
                role=message.role,
                content=message.content,
                original_created_at=message.created_at,
            )
        )
    try:
        db.commit()  # single transaction: either every message is copied or nothing is
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This visitor conversation is already attached to an account"
        ) from exc
    db.refresh(conversation)
    return _out(db, conversation, ClaimOut, already_claimed=False)


@router.get("", response_model=list[ConversationOut], summary="List your own conversations")
def list_conversations(
    identity: CandidateIdentity = Depends(require_candidate),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows = db.scalars(
        select(CandidateConversation)
        .where(CandidateConversation.candidate_id == identity.user.id)
        .order_by(CandidateConversation.created_at.desc(), CandidateConversation.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [_out(db, row) for row in rows]


@router.get(
    "/{conversation_id}", response_model=ConversationOut, summary="Read one of your conversations"
)
def get_conversation(
    conversation_id: uuid.UUID,
    identity: CandidateIdentity = Depends(require_candidate),
    db: Session = Depends(get_db),
):
    return _out(db, _owned(db, identity, conversation_id))


@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessagePage,
    summary="Paginate the messages of one of your conversations",
)
def list_conversation_messages(
    conversation_id: uuid.UUID,
    identity: CandidateIdentity = Depends(require_candidate),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    _owned(db, identity, conversation_id)
    criterion = CandidateMessage.conversation_id == conversation_id
    total = db.scalar(select(func.count()).select_from(CandidateMessage).where(criterion)) or 0
    items = db.scalars(
        select(CandidateMessage)
        .where(criterion)
        .order_by(CandidateMessage.sequence.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ConversationMessagePage(
        items=[ConversationMessageOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/{conversation_id}", status_code=204, summary="Permanently delete one of your conversations"
)
def delete_conversation(
    conversation_id: uuid.UUID,
    identity: CandidateIdentity = Depends(require_candidate),
    db: Session = Depends(get_db),
) -> Response:
    conversation = _owned(db, identity, conversation_id)
    db.delete(conversation)
    db.commit()
    return Response(status_code=204)
