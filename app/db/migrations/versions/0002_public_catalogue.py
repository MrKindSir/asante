"""Persist public landmarks and published story catalogue records."""

from alembic import op
import geoalchemy2
import sqlalchemy as sa


revision = "0002_public_catalogue"
down_revision = "0001_database_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "landmarks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("region", sa.String(length=200), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geography(
                geometry_type="POINT", srid=4326, spatial_index=False
            ),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_landmarks"),
        sa.UniqueConstraint("slug", name="uq_landmarks_slug"),
        schema="asante",
    )
    op.create_index(
        "idx_landmarks_location",
        "landmarks",
        ["location"],
        unique=False,
        schema="asante",
        postgresql_using="gist",
    )
    op.create_table(
        "stories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("contributor_name", sa.String(length=160), nullable=False),
        sa.Column("landmark_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("media_format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("media_file", sa.String(length=300), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "media_format IN ('audio', 'video')", name="ck_stories_media_format"
        ),
        sa.ForeignKeyConstraint(
            ["landmark_id"], ["asante.landmarks.id"],
            name="fk_stories_landmark_id_landmarks", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stories"),
        sa.UniqueConstraint("slug", name="uq_stories_slug"),
        schema="asante",
    )
    op.create_index(
        "idx_stories_public_status",
        "stories",
        ["status", "active"],
        unique=False,
        schema="asante",
    )
    op.create_index(
        "idx_stories_landmark_id",
        "stories",
        ["landmark_id"],
        unique=False,
        schema="asante",
    )


def downgrade() -> None:
    op.drop_index("idx_stories_landmark_id", table_name="stories", schema="asante")
    op.drop_index("idx_stories_public_status", table_name="stories", schema="asante")
    op.drop_table("stories", schema="asante")
    op.drop_index("idx_landmarks_location", table_name="landmarks", schema="asante")
    op.drop_table("landmarks", schema="asante")
