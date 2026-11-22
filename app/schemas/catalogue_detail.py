"""Typed contracts for programme specializations, courses, admission and tuition."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class SourceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    official_source_url: HttpUrl | None = Field(default=None, max_length=500)
    verified_at: datetime | None = None




class PublicationStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class PaymentMode(str, Enum):
    FULL = "FULL"
    INSTALLMENTS = "INSTALLMENTS"


class _Validity(BaseModel):
    """Validity period: bounds are timezone-aware, stored in UTC; an empty bound means unlimited."""
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def to_utc(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def end_after_start(self):
        if self.valid_from is not None and self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class PublishCreateFields(_Validity):
    publication_status: PublicationStatus = PublicationStatus.PUBLISHED


class PublishPatchFields(_Validity):
    publication_status: PublicationStatus | None = None


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


class AdmissionCreate(PublishCreateFields, SourceFields):
    kind: AdmissionKind
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=2, max_length=5000)


class AdmissionPatch(PublishPatchFields, SourceFields):
    kind: AdmissionKind | None = None
    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, min_length=2, max_length=5000)


class TuitionCreate(PublishCreateFields, SourceFields):
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


class TuitionPatch(PublishPatchFields, SourceFields):
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


class PublicationOut(BaseModel):
    publication_status: PublicationStatus
    valid_from: datetime | None
    valid_to: datetime | None


class AdmissionOut(PublicationOut, DetailOut):
    kind: AdmissionKind
    title: str
    description: str


class TuitionOut(PublicationOut, DetailOut):
    label: str
    amount: Decimal
    currency: str
    academic_year: str
    note: str | None


def _consecutive_years(year: str | None) -> str | None:
    if year is not None and int(year[5:]) != int(year[:4]) + 1:
        raise ValueError("Academic year must contain consecutive calendar years")
    return year


class PaymentTermCreate(PublishCreateFields, SourceFields):
    label: str = Field(min_length=2, max_length=180)
    academic_year: str = Field(pattern=r"^20\d{2}-20\d{2}$")
    payment_mode: PaymentMode
    installments_count: int | None = Field(default=None, ge=2, le=12)
    first_payment_percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    schedule_description: str | None = Field(default=None, max_length=5000)
    note: str | None = Field(default=None, max_length=5000)

    _year = field_validator("academic_year")(_consecutive_years)

    @model_validator(mode="after")
    def mode_matches_installments(self):
        if self.payment_mode == PaymentMode.FULL and self.installments_count is not None:
            raise ValueError("installments_count must be empty for a FULL payment")
        if self.payment_mode == PaymentMode.INSTALLMENTS and self.installments_count is None:
            raise ValueError("installments_count (2 to 12) is required for INSTALLMENTS")
        return self


class PaymentTermPatch(PublishPatchFields, SourceFields):
    label: str | None = Field(default=None, min_length=2, max_length=180)
    academic_year: str | None = Field(default=None, pattern=r"^20\d{2}-20\d{2}$")
    payment_mode: PaymentMode | None = None
    installments_count: int | None = Field(default=None, ge=2, le=12)
    first_payment_percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    schedule_description: str | None = Field(default=None, max_length=5000)
    note: str | None = Field(default=None, max_length=5000)

    _year = field_validator("academic_year")(_consecutive_years)


class PaymentTermOut(PublicationOut, DetailOut):
    label: str
    academic_year: str
    payment_mode: PaymentMode
    installments_count: int | None
    first_payment_percent: Decimal | None
    schedule_description: str | None
    note: str | None
