"""Add story poster keys and HLS derivative kinds."""

from alembic import op
import sqlalchemy as sa

revision = "0007_hls_posters"
down_revision = "0006_media_verifier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column("poster_file", sa.String(length=300), nullable=True),
        schema="asante",
    )
    op.drop_constraint("ck_derivative_kind", "media_derivatives", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_derivative_kind",
        "media_derivatives",
        "kind IN ('audio_track', 'poster', 'keyframe', 'hls_playlist')",
        schema="asante",
    )


def downgrade() -> None:
    op.drop_constraint("ck_derivative_kind", "media_derivatives", schema="asante", type_="check")
    op.create_check_constraint(
        "ck_derivative_kind",
        "media_derivatives",
        "kind IN ('audio_track', 'poster', 'keyframe')",
        schema="asante",
    )
    op.drop_column("stories", "poster_file", schema="asante")
