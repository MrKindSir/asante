"""SQLAlchemy metadata shared by Asante database migrations and services."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, Uuid, Integer, DateTime, UniqueConstraint, text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for feature-owned models in the ``asante`` schema."""

    metadata_schema = "asante"


Base.metadata.schema = Base.metadata_schema


class LandmarkRecord(Base):
    """Public landmark location used to anchor published stories."""

    __tablename__ = "landmarks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    stories: Mapped[list[StoryRecord]] = relationship(back_populates="landmark")

    __table_args__ = (
        Index("idx_landmarks_location", "location", postgresql_using="gist"),
    )


class StoryRecord(Base):
    """Published catalogue projection; contributor drafts belong to later slices."""

    __tablename__ = "stories"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    contributor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    contributor_id: Mapped[str | None] = mapped_column(ForeignKey("asante.contributors.id"), nullable=True, index=True)
    landmark_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asante.landmarks.id", ondelete="RESTRICT"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    media_format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    media_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    poster_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    transcript: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translation_language: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    caption_tracks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    landmark: Mapped[LandmarkRecord] = relationship(back_populates="stories")

    __table_args__ = (
        CheckConstraint("media_format IN ('audio', 'video')", name="ck_stories_media_format"),
        Index("idx_stories_public_status", "status", "active"),
        Index("idx_stories_landmark_id", "landmark_id"),
    )


class ContributorRecord(Base):
    __tablename__ = "contributors"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class WorkspaceSession(Base):
    __tablename__ = "workspace_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    contributor_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectRecord(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contributor_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ProjectRevision(Base):
    __tablename__ = "project_revisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("asante.projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_project_revision"),)


class UploadRecord(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("asante.projects.id"), nullable=False, index=True)
    contributor_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    consent_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SubmissionPacket(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contributor_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("asante.projects.id"), nullable=False, unique=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("asante.project_revisions.id"), nullable=False)
    upload_id: Mapped[str | None] = mapped_column(ForeignKey("asante.uploads.id"), nullable=True)
    packet: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class DecisionRecord(Base):
    __tablename__ = "review_decisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("asante.submissions.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("asante.accounts.id"), nullable=True)
    assessment_version: Mapped[str] = mapped_column(String(180), nullable=False, default="legacy/unrecorded")


class AccountRecord(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contributor_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    __table_args__ = (CheckConstraint("role IN ('contributor', 'reviewer')", name="ck_account_role"),)


class AccountSession(Base):
    __tablename__ = "account_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("asante.accounts.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    window_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanShareRecord(Base):
    __tablename__ = "plan_shares"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("asante.projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    document: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanCollaboratorRecord(Base):
    __tablename__ = "plan_collaborators"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    share_id: Mapped[str] = mapped_column(ForeignKey("asante.plan_shares.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("asante.accounts.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    invited_by: Mapped[str | None] = mapped_column(ForeignKey("asante.accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("share_id", "account_id", name="uq_plan_collaborators_share_account"),
        CheckConstraint("role IN ('reader', 'editor')", name="ck_plan_collaborators_role"),
    )


class WorkerRunRecord(Base):
    __tablename__ = "worker_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("asante.projects.id"), nullable=False, index=True)
    contributor_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False, index=True)
    worker_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    safe_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "worker_type IN ('planner', 'researcher', 'verifier', 'media', 'transcribe', 'translate', 'analyze')",
            name="ck_worker_type",
        ),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_worker_status"),
    )


class MediaDerivativeRecord(Base):
    __tablename__ = "media_derivatives"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("asante.uploads.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    object_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ready")
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        CheckConstraint(
            "kind IN ('audio_track', 'poster', 'keyframe', 'hls_playlist')",
            name="ck_derivative_kind",
        ),
        CheckConstraint("status IN ('ready', 'failed')", name="ck_derivative_status"),
    )


class ProcessingJobRecord(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("asante.submissions.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("asante.projects.id"), nullable=False)
    contributor_id: Mapped[str] = mapped_column(ForeignKey("asante.contributors.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    safe_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lease_owner: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('assessment', 'relevance', 'transcribe', 'translate', 'analyze')",
            name="ck_processing_job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_processing_job_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_processing_job_progress"),
        Index(
            "uq_processing_jobs_submission_assessment",
            "submission_id",
            unique=True,
            postgresql_where=sql_text("job_type = 'assessment'"),
        ),
    )
