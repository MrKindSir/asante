"""Allow optional contributor-provided PDF supporting documents."""

from alembic import op
import sqlalchemy as sa


revision = "0015_supporting_documents"
down_revision = "0014_merge_review_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("uploads", sa.Column("purpose", sa.String(length=30), nullable=False, server_default="media"), schema="asante")
    op.create_check_constraint(
        "ck_uploads_purpose",
        "uploads",
        "purpose IN ('media', 'supporting_document')",
        schema="asante",
    )
    op.alter_column("uploads", "purpose", server_default=None, schema="asante")


def downgrade() -> None:
    op.drop_constraint("ck_uploads_purpose", "uploads", schema="asante", type_="check")
    op.drop_column("uploads", "purpose", schema="asante")
