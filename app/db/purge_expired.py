"""Atomic retention purge: expired visitors/messages, staff & candidate tokens and rate buckets.

Run on a schedule via the Docker 'retention' service, or manually:
    docker compose exec -T api python -m app.db.purge_expired
"""

from datetime import datetime, timezone

from sqlalchemy import delete

from app.db.session import get_session_factory
from app.models.candidate import CandidateEmailToken, CandidateSession
from app.models.rate_limit import RateLimitBucket
from app.models.staff import StaffSession
from app.models.visitor import VisitorSession


def purge_all_expired() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    with get_session_factory()() as db, db.begin():
        expired_visitors = (
            db.execute(delete(VisitorSession).where(VisitorSession.expires_at <= now)).rowcount or 0
        )
        expired_staff = (
            db.execute(delete(StaffSession).where(StaffSession.expires_at <= now)).rowcount or 0
        )
        expired_candidates = (
            db.execute(delete(CandidateSession).where(CandidateSession.expires_at <= now)).rowcount
            or 0
        )
        expired_email_tokens = (
            db.execute(
                delete(CandidateEmailToken).where(CandidateEmailToken.expires_at <= now)
            ).rowcount
            or 0
        )
        expired_buckets = (
            db.execute(delete(RateLimitBucket).where(RateLimitBucket.expires_at <= now)).rowcount
            or 0
        )
    return {
        "visitor_sessions": expired_visitors,
        "staff_sessions": expired_staff,
        "candidate_sessions": expired_candidates,
        "email_tokens": expired_email_tokens,
        "rate_limit_buckets": expired_buckets,
    }


def purge_expired() -> int:
    """Backward-compatible visitor-only count; now also cleans other expired data."""
    return purge_all_expired()["visitor_sessions"]


if __name__ == "__main__":
    print(f"Retention cleanup: {purge_all_expired()}")
