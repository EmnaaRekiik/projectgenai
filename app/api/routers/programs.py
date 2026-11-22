import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    StaffIdentity,
    require_catalogue_editor,
    require_catalogue_reader,
    require_same_institution,
)
from app.db.session import get_db
from app.models import Institution, Program
from app.schemas.program import Level, Page, ProgramCreate, ProgramOut, ProgramPatch, ProgramStatus

router = APIRouter(prefix="/programs", tags=["Programmes publics"])
admin_router = APIRouter(
    prefix="/admin/programs",
    tags=["Administration des programmes"],
    dependencies=[Depends(require_catalogue_reader)],
)


def _program_or_404(db: Session, program_id: uuid.UUID) -> Program:
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programme not found")
    return program


def _paginate(db: Session, statement, limit: int, offset: int) -> Page[ProgramOut]:
    count_stmt = select(func.count()).select_from(statement.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(statement.order_by(Program.title, Program.id).limit(limit).offset(offset))
    )
    return Page[ProgramOut](
        items=[ProgramOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("", response_model=Page[ProgramOut], summary="Search verified published programmes")
def list_public_programs(
    institution_id: uuid.UUID | None = None,
    level: Level | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[ProgramOut]:
    stmt = select(Program).where(Program.status == ProgramStatus.PUBLISHED.value)
    if institution_id is not None:
        stmt = stmt.where(Program.institution_id == institution_id)
    if level is not None:
        stmt = stmt.where(Program.level == level.value)
    if q is not None:
        stmt = stmt.where(
            or_(
                Program.title.icontains(q, autoescape=True),
                Program.code.icontains(q, autoescape=True),
                Program.description.icontains(q, autoescape=True),
            )
        )
    return _paginate(db, stmt, limit, offset)


@router.get("/{program_id}", response_model=ProgramOut, summary="Read a published programme")
def get_public_program(program_id: uuid.UUID, db: Session = Depends(get_db)) -> Program:
    program = _program_or_404(db, program_id)
    if program.status != ProgramStatus.PUBLISHED.value:
        raise HTTPException(status_code=404, detail="Programme not found")
    return program


@admin_router.get(
    "", response_model=Page[ProgramOut], summary="List drafts and published programmes"
)
def list_admin_programs(
    status_filter: ProgramStatus | None = Query(default=None, alias="status"),
    institution_id: uuid.UUID | None = None,
    level: Level | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_reader),
) -> Page[ProgramOut]:
    stmt = select(Program)
    if identity.user.institution_id is not None:
        stmt = stmt.where(Program.institution_id == identity.user.institution_id)
    if status_filter is not None:
        stmt = stmt.where(Program.status == status_filter.value)
    if institution_id is not None:
        stmt = stmt.where(Program.institution_id == institution_id)
    if level is not None:
        stmt = stmt.where(Program.level == level.value)
    if q is not None:
        stmt = stmt.where(
            or_(
                Program.title.icontains(q, autoescape=True),
                Program.code.icontains(q, autoescape=True),
                Program.description.icontains(q, autoescape=True),
            )
        )
    return _paginate(db, stmt, limit, offset)


@admin_router.get("/{program_id}", response_model=ProgramOut, summary="Read any programme")
def get_admin_program(
    program_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_reader),
) -> Program:
    program = _program_or_404(db, program_id)
    require_same_institution(identity, program.institution_id)
    return program


@admin_router.post(
    "",
    response_model=ProgramOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a programme as a draft",
)
def create_program(
    payload: ProgramCreate,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
) -> Program:
    require_same_institution(identity, payload.institution_id)
    if db.get(Institution, payload.institution_id) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    data = payload.model_dump(mode="python")
    data["level"] = payload.level.value
    data["official_source_url"] = (
        str(payload.official_source_url) if payload.official_source_url else None
    )
    data["status"] = ProgramStatus.DRAFT.value
    program = Program(**data)
    db.add(program)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Programme code already exists for this institution"
        ) from exc
    db.refresh(program)
    return program


@admin_router.patch(
    "/{program_id}", response_model=ProgramOut, summary="Update or publish a programme"
)
def patch_program(
    program_id: uuid.UUID,
    payload: ProgramPatch,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
) -> Program:
    program = _program_or_404(db, program_id)
    require_same_institution(identity, program.institution_id)
    data = payload.model_dump(exclude_unset=True)
    required_fields = {"title", "level", "status"}
    if any(data.get(field, "untouched") is None for field in required_fields):
        raise HTTPException(status_code=422, detail="Required field cannot be null")
    for field, value in data.items():
        if field in {"status", "level"} and value is not None:
            value = value.value
        elif field == "official_source_url" and value is not None:
            value = str(value)
        setattr(program, field, value)

    if program.status == ProgramStatus.PUBLISHED.value:
        if not program.official_source_url or not program.verified_at:
            raise HTTPException(
                status_code=422,
                detail="Publishing requires an official source URL and verification timestamp",
            )
        if not program.official_source_url.startswith("https://"):
            raise HTTPException(status_code=422, detail="Official source URL must use HTTPS")
        verified_at = program.verified_at
        if ("verified_at" in data or "status" in data) and (
            verified_at.tzinfo is None or verified_at > datetime.now(timezone.utc)
        ):
            raise HTTPException(
                status_code=422,
                detail="Verification timestamp must be timezone-aware and in the past",
            )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Programme update conflicts with a constraint"
        ) from exc
    db.refresh(program)
    return program


@admin_router.delete(
    "/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a programme without destroying references",
)
def archive_program(
    program_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: StaffIdentity = Depends(require_catalogue_editor),
) -> Response:
    program = _program_or_404(db, program_id)
    require_same_institution(identity, program.institution_id)
    program.status = ProgramStatus.ARCHIVED.value
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
