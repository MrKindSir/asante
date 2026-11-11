"""Rebuild pending reviewer assessments from the evidence-only input contract."""

from alembic import op


revision = "0016_requeue_review_evidence_v2"
down_revision = "0015_supporting_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE asante.processing_jobs AS job
        SET status = 'queued',
            progress = 0,
            attempt = 0,
            result_payload = '{}'::jsonb,
            safe_error = '',
            lease_owner = '',
            lease_expires_at = NULL,
            started_at = NULL,
            finished_at = NULL
        FROM asante.submissions AS packet
        WHERE job.submission_id = packet.id
          AND job.job_type = 'assessment'
          AND packet.status IN ('pending_review', 'changes_requested', 'escalated')
          AND (
              job.status <> 'queued'
              OR job.result_payload <> '{}'::jsonb
              OR job.attempt <> 0
              OR job.safe_error <> ''
          )
    """)


def downgrade() -> None:
    # Assessment result snapshots are intentionally not restorable after being cleared.
    pass
