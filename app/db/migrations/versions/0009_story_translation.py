"""Persist reviewed translation text on published catalogue stories."""

from alembic import op
import sqlalchemy as sa

revision = "0009_story_translation"
down_revision = "0008_processing_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column("translation", sa.Text(), nullable=False, server_default=""),
        schema="asante",
    )
    op.add_column(
        "stories",
        sa.Column("translation_language", sa.String(length=20), nullable=False, server_default=""),
        schema="asante",
    )


def downgrade() -> None:
    op.drop_column("stories", "translation_language", schema="asante")
    op.drop_column("stories", "translation", schema="asante")
