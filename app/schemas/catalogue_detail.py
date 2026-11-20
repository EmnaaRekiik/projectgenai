"""Typed contracts for programme specializations, courses, admission and tuition."""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class SourceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    official_source_url: HttpUrl | None = Field(default=None, max_length=500)
    verified_at: datetime | None = None




class DetailPatch(SourceFields):
    """Patch fields handled with exclude_unset; use a separate serializer per kind."""
    pass


class SpecializationCreate(SourceFields):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    title: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=5000)


class SpecializationPatch(SourceFields):
    code: str | None = Field(default=None, min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=5000)


class CourseCreate(SourceFields):
    specialization_id: uuid.UUID | None = None
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    title: str = Field(min_length=2, max_length=180)
    semester: int = Field(ge=1, le=20)
    credits: int | None = Field(default=None, ge=0, le=60)
    description: str | None = Field(default=None, max_length=5000)


class CoursePatch(SourceFields):
    specialization_id: uuid.UUID | None = None
    code: str | None = Field(default=None, min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    title: str | None = Field(default=None, min_length=2, max_length=180)
    semester: int | None = Field(default=None, ge=1, le=20)
    credits: int | None = Field(default=None, ge=0, le=60)
    description: str | None = Field(default=None, max_length=5000)


class AdmissionKind(str, Enum):
    ADMISSION = "ADMISSION"
    PREREQUISITE = "PREREQUISITE"
    DOCUMENT = "DOCUMENT"


class AdmissionCreate(SourceFields):
    kind: AdmissionKind
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=2, max_length=5000)


class AdmissionPatch(SourceFields):
    kind: AdmissionKind | None = None
    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, min_length=2, max_length=5000)


class TuitionCreate(SourceFields):
    label: str = Field(min_length=2, max_length=180)
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="TND", pattern=r"^[A-Z]{3}$")
    academic_year: str = Field(pattern=r"^20\d{2}-20\d{2}$")
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("academic_year")
    @classmethod
    def contiguous_academic_year(cls, year: str) -> str:
        if int(year[5:]) != int(year[:4]) + 1:
            raise ValueError("Academic year must contain two consecutive calendar years")
        return year


class TuitionPatch(SourceFields):
    label: str | None = Field(default=None, min_length=2, max_length=180)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    academic_year: str | None = Field(default=None, pattern=r"^20\d{2}-20\d{2}$")
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("academic_year")
    @classmethod
    def contiguous_academic_year(cls, year: str | None) -> str | None:
        if year is not None and int(year[5:]) != int(year[:4]) + 1:
            raise ValueError("Academic year must contain consecutive calendar years")
        return year


class DetailOut(SourceFields):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    program_id: uuid.UUID
    created_at: datetime


class SpecializationOut(DetailOut):
    code: str
    title: str
    description: str | None


class CourseOut(DetailOut):
    specialization_id: uuid.UUID | None
    code: str
    title: str
    semester: int
    credits: int | None
    description: str | None


class AdmissionOut(DetailOut):
    kind: AdmissionKind
    title: str
    description: str


class TuitionOut(DetailOut):
    label: str
    amount: Decimal
    currency: str
    academic_year: str
    note: str | None
