"""Allow durable HLS conversion jobs after verified video uploads."""

from alembic import op


revision = "0018_hls_processing_job"
down_revision = "0017_draft_media_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_processing_job_type", "processing_jobs", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_processing_job_type",
        "processing_jobs",
        "job_type IN ('assessment', 'relevance', 'transcribe', 'translate', 'analyze', 'hls')",
        schema="asante",
    )


def downgrade() -> None:
    op.execute("DELETE FROM asante.processing_jobs WHERE job_type = 'hls'")
    op.drop_constraint("ck_processing_job_type", "processing_jobs", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_processing_job_type",
        "processing_jobs",
        "job_type IN ('assessment', 'relevance', 'transcribe', 'translate', 'analyze')",
        schema="asante",
    )
