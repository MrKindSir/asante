"""Persist private device workspaces, upload records and human review history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_contributor_workspace"
down_revision = "0002_public_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("contributors", sa.Column("id", sa.String(64), primary_key=True), sa.Column("profile", JSONB, nullable=False), sa.Column("preferences", JSONB, nullable=False), schema="asante")
    op.create_table("workspace_sessions", sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("contributor_id", sa.String(64), sa.ForeignKey("asante.contributors.id"), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), schema="asante")
    op.create_table("projects", sa.Column("id", sa.String(64), primary_key=True), sa.Column("contributor_id", sa.String(64), sa.ForeignKey("asante.contributors.id"), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("content", JSONB, nullable=False), schema="asante")
    op.create_table("project_revisions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("project_id", sa.String(64), sa.ForeignKey("asante.projects.id"), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("content", JSONB, nullable=False), sa.UniqueConstraint("project_id", "version", name="uq_project_revision"), schema="asante")
    op.create_table("uploads", sa.Column("id", sa.String(64), primary_key=True), sa.Column("project_id", sa.String(64), sa.ForeignKey("asante.projects.id"), nullable=False), sa.Column("contributor_id", sa.String(64), sa.ForeignKey("asante.contributors.id"), nullable=False), sa.Column("object_key", sa.String(300), nullable=False, unique=True), sa.Column("name", sa.String(300), nullable=False), sa.Column("content_type", sa.String(100), nullable=False), sa.Column("size", sa.Integer, nullable=False), sa.Column("checksum", sa.String(64), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), schema="asante")
    op.create_table("submissions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("contributor_id", sa.String(64), sa.ForeignKey("asante.contributors.id"), nullable=False), sa.Column("project_id", sa.String(64), sa.ForeignKey("asante.projects.id"), nullable=False, unique=True), sa.Column("revision_id", sa.String(64), sa.ForeignKey("asante.project_revisions.id"), nullable=False), sa.Column("upload_id", sa.String(64), sa.ForeignKey("asante.uploads.id")), sa.Column("packet", JSONB, nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("version", sa.Integer, nullable=False), schema="asante")
    op.create_table("review_decisions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("submission_id", sa.String(64), sa.ForeignKey("asante.submissions.id"), nullable=False), sa.Column("action", sa.String(30), nullable=False), sa.Column("reason", sa.Text, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), schema="asante")
    for table, column in [("workspace_sessions", "contributor_id"), ("projects", "contributor_id"), ("uploads", "project_id"), ("submissions", "contributor_id"), ("review_decisions", "submission_id")]:
        op.create_index(f"ix_{table}_{column}", table, [column], schema="asante")


def downgrade() -> None:
    for table in ("review_decisions", "submissions", "uploads", "project_revisions", "projects", "workspace_sessions", "contributors"):
        op.drop_table(table, schema="asante")
