"""SQLAlchemy ORM models for BranchedMind."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base class for all models."""


class Fact(Base):
    """Structured facts with vector embeddings."""

    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_blob: Mapped[bytes | None] = mapped_column("embedding", nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(
        Enum("active", "superseded", "invalidated", name="fact_status"),
        default="active",
    )
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_facts_branch", "branch_name"),
        Index("idx_facts_category", "category"),
        Index("idx_facts_status", "status"),
        Index("idx_facts_session", "session_id"),
        Index("idx_facts_created", "created_at"),
    )


class Relation(Base):
    """Entity relationship graph."""

    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_entity: Mapped[str] = mapped_column(String(200), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(200), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_relations_source", "source_entity"),
        Index("idx_relations_target", "target_entity"),
        Index("idx_relations_type", "relation_type"),
        Index("idx_relations_branch", "branch_name"),
    )


class Observation(Base):
    """Tool call observation records."""

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_blob: Mapped[bytes | None] = mapped_column("embedding", nullable=True)
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_obs_session", "session_id"),
        Index("idx_obs_type", "observation_type"),
        Index("idx_obs_branch", "branch_name"),
        Index("idx_obs_created", "created_at"),
    )


class Session(Base):
    """Session tracking."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    parent_session: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    project_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("active", "completed", "abandoned", name="session_status"),
        default="active",
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BranchRegistry(Base):
    """Branch registry."""

    __tablename__ = "branch_registry"

    branch_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    parent_branch: Mapped[str] = mapped_column(String(100), default="main")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("active", "merged", "archived", name="branch_status"),
        default="active",
    )
    forked_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    merge_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class MergeHistory(Base):
    """Audit trail for merges."""

    __tablename__ = "merge_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_branch: Mapped[str] = mapped_column(String(100), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(100), nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    items_merged: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    items_rejected: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    conflict_resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    merged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Snapshot(Base):
    """Point-in-time snapshots."""

    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    snapshot_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
