"""Retire the abandoned project messages table; preserve the local revision ID."""

from alembic import op
import sqlalchemy as sa

revision = "0013_drop_project_messages"
down_revision = "0012_project_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("project_messages", schema="asante")


def downgrade() -> None:
    op.create_table(
        "project_messages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("asante.projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(length=64), sa.ForeignKey("asante.accounts.id"), nullable=False),
        sa.Column("author_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="asante",
    )
    op.create_index("ix_project_messages_project_created", "project_messages", ["project_id", "created_at"], schema="asante")
