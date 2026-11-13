"""Add password accounts, revocable sessions and stable story/profile ownership."""
from alembic import op
import sqlalchemy as sa

revision = "0004_accounts_and_story_profiles"
down_revision = "0003_contributor_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("contributor_id", sa.String(64), sa.ForeignKey("asante.contributors.id"), nullable=False, unique=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.CheckConstraint("role IN ('contributor', 'reviewer')", name="ck_account_role"), schema="asante")
    op.create_table("account_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("asante.accounts.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), schema="asante")
    op.create_index("ix_account_sessions_account_id", "account_sessions", ["account_id"], schema="asante")
    op.create_table("login_attempts",
        sa.Column("identity_hash", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False), schema="asante")
    op.add_column("stories", sa.Column("contributor_id", sa.String(64), nullable=True), schema="asante")
    op.create_foreign_key("fk_story_contributor", "stories", "contributors", ["contributor_id"], ["id"], source_schema="asante", referent_schema="asante")
    op.create_index("ix_stories_contributor_id", "stories", ["contributor_id"], schema="asante")
    op.add_column("review_decisions", sa.Column("reviewer_id", sa.String(64), nullable=True), schema="asante")
    op.create_foreign_key("fk_decision_reviewer", "review_decisions", "accounts", ["reviewer_id"], ["id"], source_schema="asante", referent_schema="asante")


def downgrade() -> None:
    op.drop_constraint("fk_decision_reviewer", "review_decisions", schema="asante", type_="foreignkey")
    op.drop_column("review_decisions", "reviewer_id", schema="asante")
    op.drop_index("ix_stories_contributor_id", table_name="stories", schema="asante")
    op.drop_constraint("fk_story_contributor", "stories", schema="asante", type_="foreignkey")
    op.drop_column("stories", "contributor_id", schema="asante")
    for table in ("login_attempts", "account_sessions", "accounts"):
        op.drop_table(table, schema="asante")
