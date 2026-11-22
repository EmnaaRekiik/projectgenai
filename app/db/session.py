from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().sqlalchemy_url, pool_pre_ping=True, pool_size=5, max_overflow=10
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    # get_session_factory() returns a sessionmaker, not a Session.
    # Call the factory to create a database session before entering its context.
    factory = get_session_factory()
    with factory() as session:
        yield session
