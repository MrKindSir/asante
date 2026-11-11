"""Join the retired message and submission assessment migration branches."""

revision = "0014_merge_review_schema"
down_revision = ("0013_drop_project_messages", "0013_submission_assessment")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
