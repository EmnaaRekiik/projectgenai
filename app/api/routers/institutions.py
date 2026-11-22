import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.db.session import get_db
from app.models import Institution
from app.models.staff import StaffRole
from app.schemas.institution import InstitutionCreate, InstitutionOut

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("", response_model=list[InstitutionOut], summary="List IIT / ISB institutions")
def list_institutions(db: Session = Depends(get_db)) -> list[Institution]:
    return list(db.scalars(select(Institution).order_by(Institution.code)).all())


@router.get("/{institution_id}", response_model=InstitutionOut)
def get_institution(institution_id: uuid.UUID, db: Session = Depends(get_db)) -> Institution:
    institution = db.get(Institution, institution_id)
    if institution is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return institution


@router.post(
    "",
    response_model=InstitutionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(StaffRole.PLATFORM_ADMIN))],
    summary="Add an institution (admin only)",
)
def create_institution(payload: InstitutionCreate, db: Session = Depends(get_db)) -> Institution:
    institution = Institution(**payload.model_dump())
    db.add(institution)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Institution code already exists") from exc
    db.refresh(institution)
    return institution
