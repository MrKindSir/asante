"""Project collaboration chat messages for realtime team notes."""

from alembic import op
import sqlalchemy as sa

revision = "0012_project_messages"
down_revision = "0011_plan_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.create_index(
        "ix_project_messages_project_created",
        "project_messages",
        ["project_id", "created_at"],
        schema="asante",
    )


def downgrade() -> None:
    op.drop_index("ix_project_messages_project_created", table_name="project_messages", schema="asante")
    op.drop_table("project_messages", schema="asante")
