from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", summary="Check whether the API process is alive")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready", summary="Verify database connection and required schemas")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        inspector = inspect(db.get_bind())
        required = (
            "institutions",
            "programs",
            "visitor_sessions",
            "conversation_messages",
            "staff_users",
            "staff_sessions",
            "program_specializations",
            "program_courses",
            "program_admission_rules",
            "program_tuition",
            "candidate_users",
            "candidate_sessions",
            "candidate_email_tokens",
            "rate_limit_buckets",
        )
        if not all(inspector.has_table(table) for table in required):
            raise RuntimeError("Required migrations have not been applied")
        visitor_columns = {column["name"] for column in inspector.get_columns("visitor_sessions")}
        if not {"chat_request_id", "chat_lease_until"}.issubset(visitor_columns):
            raise RuntimeError("Chat migration 0003 has not been applied")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database or schema not ready") from exc
    return {
        "status": "ready",
        "database": "connected",
        "schema": "catalogue-v2",
        "visitor_schema": "visitor-v2",
        "auth_schema": "staff-and-candidate-v1",
    }
