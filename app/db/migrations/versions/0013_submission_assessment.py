"""Store media consent scope and allow bounded submission assessment jobs."""

from alembic import op
import sqlalchemy as sa

revision = "0013_submission_assessment"
down_revision = "0012_project_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("uploads", sa.Column("consent_scope", sa.String(length=80), nullable=False, server_default=""), schema="asante")
    op.add_column("uploads", sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True), schema="asante")
    op.add_column("review_decisions", sa.Column("assessment_version", sa.String(length=180), nullable=False, server_default="legacy/unrecorded"), schema="asante")
    op.drop_constraint("ck_processing_job_type", "processing_jobs", schema="asante", type_="check")
    op.create_check_constraint("ck_processing_job_type", "processing_jobs", "job_type IN ('assessment', 'relevance', 'transcribe', 'translate', 'analyze')", schema="asante")
    op.create_index("uq_processing_jobs_submission_assessment", "processing_jobs", ["submission_id"], unique=True, schema="asante", postgresql_where=sa.text("job_type = 'assessment'"))


def downgrade() -> None:
    op.drop_index("uq_processing_jobs_submission_assessment", table_name="processing_jobs", schema="asante")
    op.drop_constraint("ck_processing_job_type", "processing_jobs", schema="asante", type_="check")
    op.create_check_constraint("ck_processing_job_type", "processing_jobs", "job_type IN ('transcribe', 'translate', 'analyze')", schema="asante")
    op.drop_column("review_decisions", "assessment_version", schema="asante")
    op.drop_column("uploads", "consent_recorded_at", schema="asante")
    op.drop_column("uploads", "consent_scope", schema="asante")
