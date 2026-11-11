"""Background processing jobs for transcript, translation and video analysis."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_processing_jobs"
down_revision = "0007_hls_posters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("submission_id", sa.String(64), sa.ForeignKey("asante.submissions.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("asante.projects.id"), nullable=False),
        sa.Column("contributor_id", sa.String(64), sa.ForeignKey("asante.contributors.id"), nullable=False),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("input_payload", postgresql.JSONB(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column("safe_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("lease_owner", sa.String(120), nullable=False, server_default=""),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "job_type IN ('transcribe', 'translate', 'analyze')",
            name="ck_processing_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_processing_job_status",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_processing_job_progress"),
        schema="asante",
    )
    op.create_index("ix_processing_jobs_submission_id", "processing_jobs", ["submission_id"], schema="asante")
    op.create_index("ix_processing_jobs_status_priority", "processing_jobs", ["status", "priority", "created_at"], schema="asante")
    op.create_index("ix_processing_jobs_lease", "processing_jobs", ["lease_expires_at"], schema="asante")

    op.drop_constraint("ck_worker_type", "worker_runs", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_worker_type",
        "worker_runs",
        "worker_type IN ('planner', 'researcher', 'verifier', 'media', 'transcribe', 'translate', 'analyze')",
        schema="asante",
    )


def downgrade() -> None:
    op.drop_constraint("ck_worker_type", "worker_runs", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_worker_type",
        "worker_runs",
        "worker_type IN ('planner', 'researcher', 'verifier', 'media')",
        schema="asante",
    )
    op.drop_index("ix_processing_jobs_lease", table_name="processing_jobs", schema="asante")
    op.drop_index("ix_processing_jobs_status_priority", table_name="processing_jobs", schema="asante")
    op.drop_index("ix_processing_jobs_submission_id", table_name="processing_jobs", schema="asante")
    op.drop_table("processing_jobs", schema="asante")
