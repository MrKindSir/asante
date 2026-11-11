"""Add media derivatives and expand worker types for verifier/media."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_media_verifier"
down_revision = "0005_worker_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_worker_type", "worker_runs", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_worker_type",
        "worker_runs",
        "worker_type IN ('planner', 'researcher', 'verifier', 'media')",
        schema="asante",
    )
    op.create_table(
        "media_derivatives",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("upload_id", sa.String(64), sa.ForeignKey("asante.uploads.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("object_key", sa.String(300), nullable=False, unique=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("kind IN ('audio_track', 'poster', 'keyframe')", name="ck_derivative_kind"),
        sa.CheckConstraint("status IN ('ready', 'failed')", name="ck_derivative_status"),
        schema="asante",
    )
    op.create_index("ix_media_derivatives_upload_id", "media_derivatives", ["upload_id"], schema="asante")


def downgrade() -> None:
    op.drop_index("ix_media_derivatives_upload_id", table_name="media_derivatives", schema="asante")
    op.drop_table("media_derivatives", schema="asante")
    op.drop_constraint("ck_worker_type", "worker_runs", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_worker_type",
        "worker_runs",
        "worker_type IN ('planner', 'researcher')",
        schema="asante",
    )
