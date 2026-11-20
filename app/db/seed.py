"""Idempotently seed institution *identifiers only*, not invented programmes."""

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import Institution

INSTITUTIONS = (
    ("IIT", "Institut International de Technologie"),
    ("ISB", "ISB"),
)


def main() -> None:
    with get_session_factory()() as session:
        for code, name in INSTITUTIONS:
            if session.scalar(select(Institution).where(Institution.code == code)) is None:
                session.add(Institution(code=code, name=name))
        session.commit()
    print("Seed complete: IIT and ISB institutions only (no invented official programmes).")


if __name__ == "__main__":
    main()
