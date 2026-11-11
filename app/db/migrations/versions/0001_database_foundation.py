"""Create the Asante namespace and enable PostGIS."""

from alembic import op


revision = "0001_database_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE SCHEMA IF NOT EXISTS asante")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS asante")
