"""SA-36/37: live LLM-backed visitor chat, with atomic two-message persistence.

A short-lived lease is committed before the network call so the database is not
locked during inference. Each successful turn commits user+assistant together.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routers.visitors import _owned_active_session, _utc, visitor_token_scheme
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.llm.context import compose_prompt, verified_programme_context
from app.llm.provider import (
    GeneratedReply,
    LLMUpstreamError,
    LLMUpstreamTimeout,
    OpenAICompatibleClient,
    get_llm_client,
)
from app.models.visitor import ConversationMessage, VisitorSession
from app.schemas.visitor import MessageOut, ModelReply, UserMessageCreate

router = APIRouter(prefix="/visitor/sessions", tags=["Chat IA — dialogue multi-tours"])


def _release_lease(db: Session, session_id: uuid.UUID, lease_id: uuid.UUID) -> None:
    """Only release our own lease (a newer request may have reclaimed an expired one)."""
    db.rollback()
    try:
        record = db.scalar(
            select(VisitorSession).where(VisitorSession.id == session_id).with_for_update()
        )
        if record is not None and record.chat_request_id == lease_id:
            record.chat_request_id = None
            record.chat_lease_until = None
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        # Do not mask the original upstream error; an expired lease can be reclaimed.


@router.post(
    "/{session_id}/chat",
    response_model=ModelReply,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message to a real configured LLM and save both turns",
    responses={
        401: {"description": "Missing visitor token"},
        404: {"description": "Incorrect visitor token / unknown session"},
        409: {"description": "Conversation already generating or message limit reached"},
        503: {"description": "No model configured"},
        502: {"description": "Model provider unavailable or malformed response"},
        504: {"description": "Model provider timed out"},
    },
)
def chat(
    session_id: uuid.UUID,
    payload: UserMessageCreate,
    token: str | None = Security(visitor_token_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: OpenAICompatibleClient = Depends(get_llm_client),
) -> ModelReply:
    now = datetime.now(timezone.utc)
    record = _owned_active_session(session_id, db, token, for_update=True)
    if not settings.llm_base_url or not settings.llm_model:
        raise HTTPException(status_code=503, detail="LLM is not configured on the server")
    if record.chat_lease_until is not None and _utc(record.chat_lease_until) > now:
        raise HTTPException(status_code=409, detail="Another chat response is in progress")
    if record.next_message_sequence + 1 > settings.visitor_max_messages:
        raise HTTPException(status_code=409, detail="Not enough space for a full chat turn")

    lease_id = uuid.uuid4()
    record.chat_request_id = lease_id
    record.chat_lease_until = now + timedelta(seconds=settings.llm_timeout_seconds + 30)
    db.commit()  # release row lock BEFORE LLM inference

    try:
        recent = list(db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.sequence.desc())
            .limit(settings.llm_context_messages + 1)
        ))
        history = list(reversed(recent[: settings.llm_context_messages]))
        truncated = len(recent) > settings.llm_context_messages
        catalogue, sources = verified_programme_context(db)
        messages, budget_truncated = compose_prompt(history, payload.content, catalogue)
        truncated = truncated or budget_truncated
        db.rollback()  # don't pin DB connection while calling the model

        try:
            result: GeneratedReply = provider.generate(messages, settings)
        except LLMUpstreamTimeout as exc:
            raise HTTPException(status_code=504, detail="Language model timed out") from exc
        except LLMUpstreamError as exc:
            raise HTTPException(status_code=502, detail="Language model unavailable") from exc
        # Test doubles and custom model providers must respect the same output constraints.
        if not isinstance(result.content, str) or not result.content.strip():
            raise HTTPException(status_code=502, detail="Language model returned no text")
        if len(result.content) > settings.llm_max_response_chars:
            raise HTTPException(status_code=502, detail="Language model output too long")

        db.expire_all()  # discard pre-inference cached session state
        record = _owned_active_session(session_id, db, token, for_update=True)
        if record.chat_request_id != lease_id or (
            record.chat_lease_until is None or _utc(record.chat_lease_until) <= datetime.now(timezone.utc)
        ):
            raise HTTPException(status_code=409, detail="Chat lease expired; retry the request")
        if record.next_message_sequence + 1 > settings.visitor_max_messages:
            raise HTTPException(status_code=409, detail="Message limit reached")

        user_msg = ConversationMessage(
            session_id=session_id, role="user", sequence=record.next_message_sequence,
            content=payload.content,
        )
        assistant_msg = ConversationMessage(
            session_id=session_id, role="assistant", sequence=record.next_message_sequence + 1,
            content=result.content.strip(),
        )
        db.add_all([user_msg, assistant_msg])
        record.next_message_sequence += 2
        record.last_activity_at = datetime.now(timezone.utc)
        record.chat_request_id = None
        record.chat_lease_until = None
        db.commit()  # atomic: either BOTH messages are saved or neither
        db.refresh(user_msg)
        db.refresh(assistant_msg)
        return ModelReply(
            session_id=session_id,
            user_message=MessageOut.model_validate(user_msg),
            assistant_message=MessageOut.model_validate(assistant_msg),
            model=result.model,
            truncated_history=truncated,
            catalogue_sources=sources,
        )
    except IntegrityError as exc:
        _release_lease(db, session_id, lease_id)
        raise HTTPException(status_code=409, detail="Concurrent chat turn conflict") from exc
    except Exception:
        _release_lease(db, session_id, lease_id)
        raise
