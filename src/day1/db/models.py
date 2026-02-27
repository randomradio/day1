"""SQLAlchemy ORM models for Day1 — minimal NL-first schema."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base class for all models."""


class Memory(Base):
    """Core memory unit — NL-first, 5W coverage.

    WHO:   session_id
    WHAT:  text
    WHEN:  created_at
    WHERE: file_context (code path) + branch_name (memory branch)
    WHY:   context (NL freeform — rationale, goal, outcome)
    """

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_context: Mapped[str | None] = mapped_column(String(500), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_mem_branch", "branch_name"),
        Index("idx_mem_session", "session_id"),
        Index("idx_mem_file", "file_context"),
        Index("idx_mem_created", "created_at"),
    )


class Branch(Base):
    """Branch registry."""

    __tablename__ = "branches"

    branch_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    parent_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_branch_status", "status"),)


class Snapshot(Base):
    """PITR snapshot record."""

    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    branch_name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_snap_branch", "branch_name"),)
