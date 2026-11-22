"""Atomic PostgreSQL/SQLite rate limiting without storing plain IP addresses.

Proxy headers are deliberately ignored unless a trusted proxy policy is configured.
Fixed-window counters are shared across API workers and are pruned by retention.
"""

import hashlib
import hmac
import time
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.rate_limit import RateLimitBucket


def throttle_client(
    db: Session,
    request: Request,
    settings: Settings,
    *,
    action: str,
    limit: int,
    period_seconds: int,
) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Rate limiting secret missing")
    client_ip = request.client.host if request.client else "unknown"
    period = int(time.time()) // period_seconds
    digest = hmac.new(
        settings.admin_api_key.encode(), f"{action}:{period}:{client_ip}".encode(), hashlib.sha256
    ).hexdigest()
    expiry = datetime.fromtimestamp((period + 1) * period_seconds, timezone.utc)
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        insert = pg_insert(RateLimitBucket)
    elif dialect == "sqlite":
        insert = sqlite_insert(RateLimitBucket)
    else:
        raise RuntimeError("Rate limits require PostgreSQL or SQLite")
    stmt = insert.values(key=digest, hits=1, expires_at=expiry)
    stmt = stmt.on_conflict_do_update(
        index_elements=[RateLimitBucket.key],
        set_={"hits": RateLimitBucket.hits + 1},
        where=(RateLimitBucket.hits < limit),
    ).returning(RateLimitBucket.hits)
    hits = db.scalar(stmt)
    db.commit()
    if hits is None:
        retry = max(1, int(expiry.timestamp() - time.time()))
        raise HTTPException(
            status_code=429,
            detail="Request rate limit reached",
            headers={"Retry-After": str(retry)},
        )
