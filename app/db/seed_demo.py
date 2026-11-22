"""Insert (or remove) FICTITIOUS demonstration data for local development and demos.

    python -m app.db.seed_demo                # draft programmes + demo staff accounts
    python -m app.db.seed_demo --publish      # also make the demo data publicly visible
    python -m app.db.seed_demo --no-staff     # catalogue only
    python -m app.db.seed_demo --remove       # delete everything this script created

Safe to run several times (idempotent). Nothing here is official IIT/ISB information: titles are
prefixed "[DÉMO]", codes start with "DEMO-", and published demo data cites the reserved,
non-resolvable source https://demo.invalid/donnees-fictives. Never run --publish on a deployment
that serves real candidates.
"""

import argparse
import os
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.db import demo_data as data
from app.db.seed import INSTITUTIONS
from app.models import (
    Institution,
    Program,
    ProgramAdmissionRule,
    ProgramCourse,
    ProgramPaymentTerm,
    ProgramSpecialization,
    ProgramTuition,
    StaffUser,
)


class SeedError(RuntimeError):
    pass


@dataclass
class Report:
    created: dict = field(default_factory=dict)
    existing: dict = field(default_factory=dict)
    generated_passwords: dict = field(default_factory=dict)  # only for accounts created by this run
    published: bool = False

    def count(self, kind: str, created: bool) -> None:
        bucket = self.created if created else self.existing
        bucket[kind] = bucket.get(kind, 0) + 1


def academic_year_window(now: datetime) -> dict:
    """Academic year containing `now` (1 September to 31 August), so demo data never expires."""
    start = now.year if now.month >= 9 else now.year - 1
    utc = timezone.utc
    return {
        "label": f"{start}-{start + 1}",
        "from": datetime(start, 9, 1, tzinfo=utc),
        "to": datetime(start + 1, 8, 31, 23, 59, 59, tzinfo=utc),
        "prev_label": f"{start - 1}-{start}",
        "prev_from": datetime(start - 1, 9, 1, tzinfo=utc),
        "prev_to": datetime(start, 8, 31, 23, 59, 59, tzinfo=utc),
    }


def _get_or_create(session: Session, report: Report, kind: str, model, lookup: dict, values: dict):
    row = session.scalar(select(model).filter_by(**lookup))
    if row is None:
        row = model(**lookup, **values)
        session.add(row)
        session.flush()
        report.count(kind, True)
    else:
        report.count(kind, False)
    return row


def _evidence(row, publish: bool, now: datetime) -> None:
    if publish and (row.verified_at is None or not row.official_source_url):
        row.official_source_url = data.DEMO_SOURCE_URL
        row.verified_at = now


def seed_demo(
    session: Session,
    publish: bool = False,
    with_staff: bool = True,
    staff_password: str | None = None,
    now: datetime | None = None,
) -> Report:
    now = now or datetime.now(timezone.utc)
    window = academic_year_window(now)
    report = Report(published=publish)

    institutions = {}
    for code, name in INSTITUTIONS:
        institutions[code] = _get_or_create(
            session, Report(), "institution", Institution, {"code": code}, {"name": name}
        )

    if with_staff and session.scalar(select(func.count()).select_from(StaffUser)) == 0:
        raise SeedError(
            "No staff account exists yet. Create the real administrator first "
            "(scripts/bootstrap_admin.ps1), otherwise the one-time bootstrap would be blocked."
        )

    for spec in data.DEMO_PROGRAMS:
        program = _get_or_create(
            session,
            report,
            "programmes",
            Program,
            {"institution_id": institutions[spec["institution"]].id, "code": spec["code"]},
            {
                "title": spec["title"],
                "level": spec["level"],
                "duration_years": spec["duration_years"],
                "description": data.DEMO_NOTE,
                "status": "DRAFT",
            },
        )
        if publish:
            _evidence(program, True, now)
            program.status = "PUBLISHED"
        specializations = {}
        for code, title, description in spec["specializations"]:
            row = _get_or_create(
                session,
                report,
                "spécialités",
                ProgramSpecialization,
                {"program_id": program.id, "code": code},
                {"title": title, "description": description},
            )
            _evidence(row, publish, now)
            specializations[code] = row
        for code, title, semester, credits, spec_code in spec["courses"]:
            row = _get_or_create(
                session,
                report,
                "matières",
                ProgramCourse,
                {"program_id": program.id, "code": code, "semester": semester},
                {
                    "title": title,
                    "credits": credits,
                    "specialization_id": specializations[spec_code].id if spec_code else None,
                },
            )
            _evidence(row, publish, now)
        for kind, title, description in data.rules():
            row = _get_or_create(
                session,
                report,
                "règles d'admission",
                ProgramAdmissionRule,
                {"program_id": program.id, "kind": kind, "title": title},
                {"description": description},
            )
            _evidence(row, publish, now)
        amount = Decimal(spec["tuition"])
        for label, year, start, end, value in (
            (
                "[DÉMO] Frais annuels (montant fictif)",
                window["label"],
                window["from"],
                window["to"],
                amount,
            ),
            (
                "[DÉMO] Frais de l'année précédente (expiré)",
                window["prev_label"],
                window["prev_from"],
                window["prev_to"],
                amount - 300,
            ),
        ):
            row = _get_or_create(
                session,
                report,
                "tarifs",
                ProgramTuition,
                {
                    "program_id": program.id,
                    "label": label,
                    "academic_year": year,
                    "currency": "TND",
                },
                {"amount": value, "note": data.DEMO_NOTE, "valid_from": start, "valid_to": end},
            )
            _evidence(row, publish, now)
        for label, mode, count, percent, schedule in (
            (
                "[DÉMO] Paiement unique",
                "FULL",
                None,
                None,
                "Règlement en une fois à l'inscription (exemple fictif).",
            ),
            (
                "[DÉMO] Paiement en trois tranches",
                "INSTALLMENTS",
                3,
                Decimal("40.00"),
                "40 % à l'inscription puis deux versements égaux (exemple fictif).",
            ),
        ):
            row = _get_or_create(
                session,
                report,
                "modalités de paiement",
                ProgramPaymentTerm,
                {"program_id": program.id, "label": label, "academic_year": window["label"]},
                {
                    "payment_mode": mode,
                    "installments_count": count,
                    "first_payment_percent": percent,
                    "schedule_description": schedule,
                    "note": data.DEMO_NOTE,
                    "valid_from": window["from"],
                    "valid_to": window["to"],
                },
            )
            _evidence(row, publish, now)

    if with_staff:
        password = staff_password
        for email, name, role, institution_code in data.DEMO_STAFF:
            if session.scalar(select(StaffUser).where(StaffUser.email == email)) is not None:
                report.count("comptes responsables", False)
                continue
            plain = password or secrets.token_urlsafe(16)
            session.add(
                StaffUser(
                    email=email,
                    display_name=name,
                    password_hash=hash_password(plain),
                    role=role,
                    institution_id=institutions[institution_code].id if institution_code else None,
                    is_active=True,
                    failed_login_count=0,
                )
            )
            report.generated_passwords[email] = None if password else plain
            report.count("comptes responsables", True)
    session.commit()
    return report


def remove_demo(session: Session) -> dict:
    """Delete demo programmes (children first: the course/specialization key is RESTRICT) and demo staff."""
    removed = {"programmes": 0, "comptes responsables": 0, "programmes conservés": 0}
    for program in session.scalars(
        select(Program).where(Program.code.like(data.DEMO_PREFIX + "%"))
    ).all():
        try:
            with session.begin_nested():
                for model in (
                    ProgramCourse,
                    ProgramSpecialization,
                    ProgramAdmissionRule,
                    ProgramTuition,
                    ProgramPaymentTerm,
                ):
                    session.execute(delete(model).where(model.program_id == program.id))
                session.delete(program)
                session.flush()
            removed["programmes"] += 1
        except IntegrityError:
            removed["programmes conservés"] += 1  # e.g. a candidate already preregistered to it
    emails = [row[0] for row in data.DEMO_STAFF]
    for user in session.scalars(select(StaffUser).where(StaffUser.email.in_(emails))).all():
        session.delete(user)
        removed["comptes responsables"] += 1
    session.commit()
    return removed


def _print_report(report: Report) -> None:
    print("Données de DÉMONSTRATION (fictives) :")
    for kind in sorted(set(report.created) | set(report.existing)):
        print(
            f"  {kind}: {report.created.get(kind, 0)} créé(s), {report.existing.get(kind, 0)} déjà présent(s)"
        )
    print(
        "Statut : "
        + (
            "PUBLIÉ (source fictive https://demo.invalid, visible publiquement)"
            if report.published
            else "brouillon (invisible au public ; utiliser --publish pour l'exposer)"
        )
    )
    created = {email: pw for email, pw in report.generated_passwords.items()}
    if created:
        print(
            "\nComptes responsables créés (mots de passe affichés UNE SEULE FOIS, à noter maintenant) :"
        )
        for email, pw in created.items():
            print(f"  {email}  mot de passe : {pw if pw else '(valeur de DEMO_STAFF_PASSWORD)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--publish", action="store_true", help="make demo data publicly visible (fictitious source)"
    )
    parser.add_argument("--no-staff", action="store_true", help="do not create demo staff accounts")
    parser.add_argument(
        "--remove", action="store_true", help="delete all demo data created by this script"
    )
    args = parser.parse_args(argv)
    from app.db.session import get_session_factory

    password = os.environ.get("DEMO_STAFF_PASSWORD") or None
    if password is not None and not 12 <= len(password) <= 128:
        print("DEMO_STAFF_PASSWORD must contain 12 to 128 characters.", file=sys.stderr)
        return 2
    with get_session_factory()() as session:
        try:
            if args.remove:
                print("Supprimé :", remove_demo(session))
                return 0
            _print_report(
                seed_demo(
                    session,
                    publish=args.publish,
                    with_staff=not args.no_staff,
                    staff_password=password,
                )
            )
        except SeedError as exc:
            print(f"Arrêt : {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
