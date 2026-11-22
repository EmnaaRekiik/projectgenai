"""Typed REST endpoints for independently sourced academic programme details.

The public only sees details with verified HTTPS evidence belonging to a published programme.
Staff can create/edit drafts; modifying substantive content invalidates prior verification.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    StaffIdentity,
    require_catalogue_editor,
    require_catalogue_reader,
    require_same_institution,
)
from app.db.session import get_db
from app.models.catalogue_detail import (
    ProgramAdmissionRule,
    ProgramCourse,
    ProgramPaymentTerm,
    ProgramSpecialization,
    ProgramTuition,
)
from app.models.program import Program
from app.schemas.catalogue_detail import (
    AdmissionCreate,
    AdmissionOut,
    AdmissionPatch,
    CourseCreate,
    CourseOut,
    CoursePatch,
    PaymentTermCreate,
    PaymentTermOut,
    PaymentTermPatch,
    SpecializationCreate,
    SpecializationOut,
    SpecializationPatch,
    TuitionCreate,
    TuitionOut,
    TuitionPatch,
)
from app.schemas.program import ProgramStatus

public = APIRouter(prefix="/programs", tags=["Catalogue académique public"])
admin = APIRouter(prefix="/admin/programs", tags=["Détails académiques : administration"])


def _parent(
    db: Session, program_id: uuid.UUID, identity: StaffIdentity | None = None, public_only=False
):
    program = db.get(Program, program_id)
    if program is None or (public_only and program.status != ProgramStatus.PUBLISHED.value):
        raise HTTPException(status_code=404, detail="Programme not found")
    if identity is not None:
        require_same_institution(identity, program.institution_id)
    return program


def _item(db, program_id, item_id, model):
    item = db.get(model, item_id)
    if item is None or item.program_id != program_id:
        raise HTTPException(status_code=404, detail="Academic detail not found")
    return item


def _source_verified(item) -> bool:
    return bool(
        item.verified_at
        and item.official_source_url
        and item.official_source_url.startswith("https://")
        and (
            item.verified_at
            if item.verified_at.tzinfo
            else item.verified_at.replace(tzinfo=timezone.utc)
        )
        <= datetime.now(timezone.utc)
    )


def _translate(model_data: dict):
    for field, value in list(model_data.items()):
        if field == "official_source_url" and value is not None:
            model_data[field] = str(value)
        elif field in {"kind", "publication_status", "payment_mode"} and value is not None:
            model_data[field] = value.value
    return model_data


def _verify(item):
    if item.verified_at is None:
        return
    if not _source_verified(item):
        raise HTTPException(
            status_code=422,
            detail="Verification requires a non-future timestamp and official HTTPS source",
        )


def _validate_effective(item):
    """Checks that need the final state of the row (create, or patch merged with stored values)."""
    start, end = getattr(item, "valid_from", None), getattr(item, "valid_to", None)
    if start is not None and end is not None:
        a = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        b = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        if b <= a:
            raise HTTPException(status_code=422, detail="valid_to must be later than valid_from")
    if isinstance(item, ProgramPaymentTerm):
        if item.payment_mode == "FULL" and item.installments_count is not None:
            raise HTTPException(
                status_code=422, detail="installments_count must be empty for a FULL payment"
            )
        if item.payment_mode == "INSTALLMENTS" and item.installments_count is None:
            raise HTTPException(
                status_code=422, detail="installments_count (2 to 12) is required for INSTALLMENTS"
            )


def _commit(db: Session, item):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Academic detail conflicts with a catalogue constraint"
        ) from exc
    db.refresh(item)
    return item


def official_and_valid_now(model, now=None):
    """Conditions for what candidates and the AI agent may see: verified source, and, for
    models with a publication status, PUBLISHED and today inside the validity period."""
    now = now or datetime.now(timezone.utc)
    conditions = [
        model.verified_at.is_not(None),
        model.verified_at <= now,
        model.official_source_url.like("https://%"),
    ]
    if hasattr(model, "publication_status"):
        conditions += [
            model.publication_status == "PUBLISHED",
            or_(model.valid_from.is_(None), model.valid_from <= now),
            or_(model.valid_to.is_(None), model.valid_to >= now),
        ]
    return conditions


def _public_list(db, program_id, model, limit, offset):
    _parent(db, program_id, public_only=True)
    stmt = select(model).where(model.program_id == program_id, *official_and_valid_now(model))
    return list(db.scalars(stmt.order_by(model.created_at, model.id).offset(offset).limit(limit)))


def _admin_list(db, program_id, model, identity, limit, offset):
    _parent(db, program_id, identity)
    return list(
        db.scalars(
            select(model)
            .where(model.program_id == program_id)
            .order_by(model.created_at, model.id)
            .offset(offset)
            .limit(limit)
        )
    )


def _create(db, program_id, model, payload, identity):
    _parent(db, program_id, identity)
    item = model(program_id=program_id, **_translate(payload.model_dump(exclude_unset=True)))
    _validate_effective(item)
    _verify(item)
    db.add(item)
    return _commit(db, item)


def _patch(db, program_id, item_id, model, payload, identity):
    _parent(db, program_id, identity)
    item = _item(db, program_id, item_id, model)
    changes = _translate(payload.model_dump(exclude_unset=True))
    # Content fields: editing one removes the verified badge. Management fields
    # (publication_status) do not, but validity dates are part of the official information.
    immutable = {
        "code",
        "title",
        "specialization_id",
        "semester",
        "credits",
        "description",
        "kind",
        "label",
        "amount",
        "currency",
        "academic_year",
        "note",
        "payment_mode",
        "installments_count",
        "first_payment_percent",
        "schedule_description",
        "valid_from",
        "valid_to",
    }
    required = {
        "code",
        "title",
        "semester",
        "kind",
        "description",
        "label",
        "amount",
        "currency",
        "academic_year",
        "payment_mode",
        "publication_status",
    }
    if any(changes.get(field, "no-change") is None for field in required):
        raise HTTPException(status_code=422, detail="Required field cannot be null")
    # No stale 'verified' badge after editing a value. Require re-verification.
    if (
        immutable.intersection(changes) or "official_source_url" in changes
    ) and "verified_at" not in changes:
        item.verified_at = None
    for field, value in changes.items():
        setattr(item, field, value)
    _validate_effective(item)
    _verify(item)
    return _commit(db, item)


def _delete(db, program_id, item_id, model, identity):
    _parent(db, program_id, identity)
    item = _item(db, program_id, item_id, model)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


# Each group below supplies explicit Pydantic request/response models, so Swagger
# documents actual validation rules rather than opaque JSON dictionaries.


@public.get(
    "/{program_id}/specializations",
    response_model=list[SpecializationOut],
    summary="Public verified specializations",
)
def public_specializations(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _public_list(db, program_id, ProgramSpecialization, limit, offset)


@admin.get(
    "/{program_id}/specializations",
    response_model=list[SpecializationOut],
    summary="Staff view of all specializations",
)
def admin_specializations(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_reader),
):
    return _admin_list(db, program_id, ProgramSpecialization, identity, limit, offset)


@admin.post("/{program_id}/specializations", response_model=SpecializationOut, status_code=201)
def create_specializations(
    program_id: uuid.UUID,
    payload: SpecializationCreate,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _create(db, program_id, ProgramSpecialization, payload, identity)


@admin.patch("/{program_id}/specializations/{item_id}", response_model=SpecializationOut)
def patch_specializations(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: SpecializationPatch,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _patch(db, program_id, item_id, ProgramSpecialization, payload, identity)


@admin.delete("/{program_id}/specializations/{item_id}", status_code=204)
def delete_specializations(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _delete(db, program_id, item_id, ProgramSpecialization, identity)


@public.get(
    "/{program_id}/courses", response_model=list[CourseOut], summary="Public verified courses"
)
def public_courses(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _public_list(db, program_id, ProgramCourse, limit, offset)


@admin.get(
    "/{program_id}/courses", response_model=list[CourseOut], summary="Staff view of all courses"
)
def admin_courses(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_reader),
):
    return _admin_list(db, program_id, ProgramCourse, identity, limit, offset)


@admin.post("/{program_id}/courses", response_model=CourseOut, status_code=201)
def create_courses(
    program_id: uuid.UUID,
    payload: CourseCreate,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _create(db, program_id, ProgramCourse, payload, identity)


@admin.patch("/{program_id}/courses/{item_id}", response_model=CourseOut)
def patch_courses(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: CoursePatch,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _patch(db, program_id, item_id, ProgramCourse, payload, identity)


@admin.delete("/{program_id}/courses/{item_id}", status_code=204)
def delete_courses(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _delete(db, program_id, item_id, ProgramCourse, identity)


@public.get(
    "/{program_id}/admission-rules",
    response_model=list[AdmissionOut],
    summary="Public verified admission-rules",
)
def public_admission_rules(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _public_list(db, program_id, ProgramAdmissionRule, limit, offset)


@admin.get(
    "/{program_id}/admission-rules",
    response_model=list[AdmissionOut],
    summary="Staff view of all admission-rules",
)
def admin_admission_rules(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_reader),
):
    return _admin_list(db, program_id, ProgramAdmissionRule, identity, limit, offset)


@admin.post("/{program_id}/admission-rules", response_model=AdmissionOut, status_code=201)
def create_admission_rules(
    program_id: uuid.UUID,
    payload: AdmissionCreate,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _create(db, program_id, ProgramAdmissionRule, payload, identity)


@admin.patch("/{program_id}/admission-rules/{item_id}", response_model=AdmissionOut)
def patch_admission_rules(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: AdmissionPatch,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _patch(db, program_id, item_id, ProgramAdmissionRule, payload, identity)


@admin.delete("/{program_id}/admission-rules/{item_id}", status_code=204)
def delete_admission_rules(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _delete(db, program_id, item_id, ProgramAdmissionRule, identity)


@public.get(
    "/{program_id}/tuition", response_model=list[TuitionOut], summary="Public verified tuition"
)
def public_tuition(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _public_list(db, program_id, ProgramTuition, limit, offset)


@admin.get(
    "/{program_id}/tuition", response_model=list[TuitionOut], summary="Staff view of all tuition"
)
def admin_tuition(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_reader),
):
    return _admin_list(db, program_id, ProgramTuition, identity, limit, offset)


@admin.post("/{program_id}/tuition", response_model=TuitionOut, status_code=201)
def create_tuition(
    program_id: uuid.UUID,
    payload: TuitionCreate,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _create(db, program_id, ProgramTuition, payload, identity)


@admin.patch("/{program_id}/tuition/{item_id}", response_model=TuitionOut)
def patch_tuition(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: TuitionPatch,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _patch(db, program_id, item_id, ProgramTuition, payload, identity)


@admin.delete("/{program_id}/tuition/{item_id}", status_code=204)
def delete_tuition(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _delete(db, program_id, item_id, ProgramTuition, identity)


@public.get(
    "/{program_id}/payment-terms",
    response_model=list[PaymentTermOut],
    summary="Public verified, published and currently valid payment terms",
)
def public_payment_terms(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _public_list(db, program_id, ProgramPaymentTerm, limit, offset)


@admin.get(
    "/{program_id}/payment-terms",
    response_model=list[PaymentTermOut],
    summary="Staff view of all payment terms",
)
def admin_payment_terms(
    program_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_reader),
):
    return _admin_list(db, program_id, ProgramPaymentTerm, identity, limit, offset)


@admin.post("/{program_id}/payment-terms", response_model=PaymentTermOut, status_code=201)
def create_payment_terms(
    program_id: uuid.UUID,
    payload: PaymentTermCreate,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _create(db, program_id, ProgramPaymentTerm, payload, identity)


@admin.patch("/{program_id}/payment-terms/{item_id}", response_model=PaymentTermOut)
def patch_payment_terms(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: PaymentTermPatch,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _patch(db, program_id, item_id, ProgramPaymentTerm, payload, identity)


@admin.delete("/{program_id}/payment-terms/{item_id}", status_code=204)
def delete_payment_terms(
    program_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
):
    return _delete(db, program_id, item_id, ProgramPaymentTerm, identity)
