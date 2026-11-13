"""Persist Asante AI worker runs for planner and researcher."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_worker_runs"
down_revision = "0004_accounts_and_story_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("asante.projects.id"), nullable=False),
        sa.Column("contributor_id", sa.String(64), sa.ForeignKey("asante.contributors.id"), nullable=False),
        sa.Column("worker_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column("safe_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("provider_model", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("worker_type IN ('planner', 'researcher')", name="ck_worker_type"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_worker_status"),
        schema="asante",
    )
    op.create_index("ix_worker_runs_project_id", "worker_runs", ["project_id"], schema="asante")
    op.create_index("ix_worker_runs_contributor_id", "worker_runs", ["contributor_id"], schema="asante")
    op.create_index("ix_worker_runs_trace_id", "worker_runs", ["trace_id"], schema="asante")


def downgrade() -> None:
    op.drop_index("ix_worker_runs_trace_id", table_name="worker_runs", schema="asante")
    op.drop_index("ix_worker_runs_contributor_id", table_name="worker_runs", schema="asante")
    op.drop_index("ix_worker_runs_project_id", table_name="worker_runs", schema="asante")
    op.drop_table("worker_runs", schema="asante")
