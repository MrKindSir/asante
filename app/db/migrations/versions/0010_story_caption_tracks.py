"""Timed caption tracks for published catalogue stories."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_story_caption_tracks"
down_revision = "0009_story_translation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column(
            "caption_tracks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="asante",
    )


def downgrade() -> None:
    op.drop_column("stories", "caption_tracks", schema="asante")
