"""Shared field-report documents and collaborator roles."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_plan_shares"
down_revision = "0010_story_caption_tracks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_shares",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("asante.projects.id"), nullable=False, unique=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("asante.contributors.id"), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False, unique=True),
        sa.Column("title", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="asante",
    )
    op.create_table(
        "plan_collaborators",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("share_id", sa.String(length=64), sa.ForeignKey("asante.plan_shares.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(length=64), sa.ForeignKey("asante.accounts.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("invited_by", sa.String(length=64), sa.ForeignKey("asante.accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("share_id", "account_id", name="uq_plan_collaborators_share_account"),
        sa.CheckConstraint("role IN ('reader', 'editor')", name="ck_plan_collaborators_role"),
        schema="asante",
    )
    op.create_index("ix_plan_shares_token", "plan_shares", ["token"], unique=True, schema="asante")
    op.create_index("ix_plan_collaborators_share_id", "plan_collaborators", ["share_id"], schema="asante")


def downgrade() -> None:
    op.drop_index("ix_plan_collaborators_share_id", table_name="plan_collaborators", schema="asante")
    op.drop_index("ix_plan_shares_token", table_name="plan_shares", schema="asante")
    op.drop_table("plan_collaborators", schema="asante")
    op.drop_table("plan_shares", schema="asante")
