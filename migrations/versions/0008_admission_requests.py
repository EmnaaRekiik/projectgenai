"""Preinscriptions, equivalence requests, appointments and interview results (additive).

Revision ID: 0008_admission_requests
Revises: 0007_abuse_limits
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_admission_requests"
down_revision = "0007_abuse_limits"
branch_labels = None
depends_on = None


def _in(column, values):
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


def _now():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _updated():
    return sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table("preregistrations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(as_uuid=True), sa.ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("program_id", sa.Uuid(as_uuid=True), sa.ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("consent_given_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.Uuid(as_uuid=True), sa.ForeignKey("staff_users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_note", sa.Text()),
        _now(), _updated(),
        sa.CheckConstraint(_in("status", ("DRAFT", "SUBMITTED", "COMPLETE", "VALIDATED", "REJECTED", "CANCELLED")), name="ck_prereg_status"),
        sa.CheckConstraint("status = 'DRAFT' OR consent_given_at IS NOT NULL", name="ck_prereg_consent_required"))
    op.create_index("ix_prereg_candidate", "preregistrations", ["candidate_id"])
    op.create_index("ix_prereg_program_status", "preregistrations", ["program_id", "status"])

    op.create_table("equivalence_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(as_uuid=True), sa.ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_program_id", sa.Uuid(as_uuid=True), sa.ForeignKey("programs.id", ondelete="SET NULL")),
        sa.Column("origin_diploma", sa.String(180), nullable=False),
        sa.Column("origin_institution", sa.String(180), nullable=False),
        sa.Column("origin_country", sa.String(80)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decision_note", sa.Text()),
        sa.Column("reviewed_by", sa.Uuid(as_uuid=True), sa.ForeignKey("staff_users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        _now(), _updated(),
        sa.CheckConstraint(_in("status", ("DRAFT", "SUBMITTED", "IN_REVIEW", "INFO_REQUESTED", "ACCEPTED", "REFUSED")), name="ck_equivalence_status"))
    op.create_index("ix_equivalence_candidate", "equivalence_requests", ["candidate_id"])
    op.create_index("ix_equivalence_status", "equivalence_requests", ["status"])

    op.create_table("appointments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(as_uuid=True), sa.ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("preregistration_id", sa.Uuid(as_uuid=True), sa.ForeignKey("preregistrations.id", ondelete="SET NULL")),
        sa.Column("manager_id", sa.Uuid(as_uuid=True), sa.ForeignKey("staff_users.id", ondelete="SET NULL")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("location_or_link", sa.String(500)),
        _now(), _updated(),
        sa.CheckConstraint(_in("status", ("PROPOSED", "CONFIRMED", "RESCHEDULED", "CANCELLED", "COMPLETED")), name="ck_appointment_status"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_appointment_time_order"))
    op.create_index("ix_appointment_candidate", "appointments", ["candidate_id"])
    op.create_index("ix_appointment_manager_start", "appointments", ["manager_id", "starts_at"])

    op.create_table("interview_results",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("qcm_score", sa.Numeric(5, 2)),
        sa.Column("summary", sa.Text()),
        sa.Column("decision", sa.String(16)),
        sa.Column("observations", sa.Text()),
        sa.Column("recorded_by", sa.Uuid(as_uuid=True), sa.ForeignKey("staff_users.id", ondelete="SET NULL")),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
        _now(),
        sa.UniqueConstraint("appointment_id", name="uq_interview_appointment"),
        sa.CheckConstraint(_in("status", ("PLANNED", "QCM_SENT", "QCM_DONE", "HELD", "RESULT_RECORDED")), name="ck_interview_status"),
        sa.CheckConstraint("decision IS NULL OR " + _in("decision", ("ADMITTED", "WAITLIST", "REFUSED", "INFO_NEEDED")), name="ck_interview_decision"),
        sa.CheckConstraint("qcm_score IS NULL OR (qcm_score >= 0 AND qcm_score <= 100)", name="ck_interview_qcm_score"),
        sa.CheckConstraint("decision IS NULL OR status = 'RESULT_RECORDED'", name="ck_interview_decision_status"))


def downgrade():
    op.drop_table("interview_results")
    op.drop_index("ix_appointment_manager_start", table_name="appointments")
    op.drop_index("ix_appointment_candidate", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index("ix_equivalence_status", table_name="equivalence_requests")
    op.drop_index("ix_equivalence_candidate", table_name="equivalence_requests")
    op.drop_table("equivalence_requests")
    op.drop_index("ix_prereg_program_status", table_name="preregistrations")
    op.drop_index("ix_prereg_candidate", table_name="preregistrations")
    op.drop_table("preregistrations")
