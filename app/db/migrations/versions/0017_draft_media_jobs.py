"""Allow draft media processing jobs before submission."""

from alembic import op
import sqlalchemy as sa


revision = "0017_draft_media_jobs"
down_revision = "0016_requeue_review_evidence_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "processing_jobs",
        "submission_id",
        existing_type=sa.String(length=64),
        nullable=True,
        schema="asante",
    )
    op.create_index(
        "ix_processing_jobs_project_draft",
        "processing_jobs",
        ["project_id", "job_type", "created_at"],
        schema="asante",
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_project_draft", table_name="processing_jobs", schema="asante")
    op.execute("""
        DELETE FROM asante.processing_jobs
        WHERE submission_id IS NULL
    """)
    op.alter_column(
        "processing_jobs",
        "submission_id",
        existing_type=sa.String(length=64),
        nullable=False,
        schema="asante",
    )
