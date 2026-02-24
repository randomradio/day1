"""SQLAlchemy ORM models for Day1 (MatrixOne backend)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class JsonText(TypeDecorator):
    """JSON stored as TEXT for MO DATA BRANCH DIFF compatibility.

    MO's DATA BRANCH DIFF cannot handle MySQL type 245 (JSON) in result
    sets.  This type stores JSON-serialised TEXT in the database so DIFF
    works, while presenting ``dict`` / ``list`` to Python code.

    Use on branch-participating tables (facts, relations, observations).
    Non-branched tables (sessions, snapshots, …) can keep native JSON.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return None


class Base(DeclarativeBase):
    """Base class for all models."""


class Fact(Base):
    """Structured facts with vector embeddings."""

    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JsonText, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_facts_branch", "branch_name"),
        Index("idx_facts_category", "category"),
        Index("idx_facts_status", "status"),
        Index("idx_facts_session", "session_id"),
        Index("idx_facts_created", "created_at"),
        Index("idx_facts_task", "task_id"),
        Index("idx_facts_agent", "agent_id"),
    )


class Relation(Base):
    """Entity relationship graph."""

    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_entity: Mapped[str] = mapped_column(String(200), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(200), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JsonText, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    valid_from: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_relations_source", "source_entity"),
        Index("idx_relations_target", "target_entity"),
        Index("idx_relations_type", "relation_type"),
        Index("idx_relations_branch", "branch_name"),
        Index("idx_relations_task", "task_id"),
    )


class Observation(Base):
    """Tool call observation records."""

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_observation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JsonText, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_obs_session", "session_id"),
        Index("idx_obs_type", "observation_type"),
        Index("idx_obs_branch", "branch_name"),
        Index("idx_obs_created", "created_at"),
        Index("idx_obs_task", "task_id"),
        Index("idx_obs_agent", "agent_id"),
    )


class Session(Base):
    """Session tracking."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    parent_session: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    project_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BranchRegistry(Base):
    """Branch registry."""

    __tablename__ = "branch_registry"

    branch_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    parent_branch: Mapped[str] = mapped_column(String(100), default="main")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    forked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    merge_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Snapshot(Base):
    """Point-in-time snapshots."""

    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    snapshot_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# === Multi-Agent Task Memory ===


class Task(Base):
    """A long-running task that groups multiple agents and sessions."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    parent_branch: Mapped[str] = mapped_column(String(100), default="main")
    status: Mapped[str] = mapped_column(String(20), default="active")
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    objectives: Mapped[list | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_branch", "branch_name"),
        Index("idx_tasks_type", "task_type"),
    )


class TaskAgent(Base):
    """An agent assigned to a task."""

    __tablename__ = "task_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    assigned_objectives: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_task_agents_task", "task_id"),
        Index("idx_task_agents_agent", "agent_id"),
        Index("idx_task_agents_branch", "branch_name"),
    )


# === Conversation & Message History Layer ===


class Conversation(Base):
    """A conversation thread — the unit of chat history."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    fork_point_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JsonText, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_conv_session", "session_id"),
        Index("idx_conv_agent", "agent_id"),
        Index("idx_conv_task", "task_id"),
        Index("idx_conv_branch", "branch_name"),
        Index("idx_conv_status", "status"),
        Index("idx_conv_created", "created_at"),
    )


class Message(Base):
    """A single message in a conversation — branchable via DATA BRANCH."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls_json: Mapped[dict | None] = mapped_column(
        "tool_calls", JsonText, nullable=True
    )
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sequence_num: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JsonText, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_msg_conversation", "conversation_id"),
        Index("idx_msg_session", "session_id"),
        Index("idx_msg_agent", "agent_id"),
        Index("idx_msg_role", "role"),
        Index("idx_msg_branch", "branch_name"),
        Index("idx_msg_sequence", "conversation_id", "sequence_num"),
        Index("idx_msg_created", "created_at"),
    )


class ConsolidationHistory(Base):
    """Audit trail for memory consolidation events."""

    __tablename__ = "consolidation_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consolidation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_branch: Mapped[str] = mapped_column(String(100), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(100), nullable=False)
    facts_created: Mapped[int] = mapped_column(Integer, default=0)
    facts_updated: Mapped[int] = mapped_column(Integer, default=0)
    facts_deduplicated: Mapped[int] = mapped_column(Integer, default=0)
    observations_processed: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# === Scoring ===


class Score(Base):
    """A score applied to a message, conversation, or replay."""

    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scorer: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JsonText, nullable=True
    )
    branch_name: Mapped[str] = mapped_column(String(100), default="main")
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_score_target", "target_type", "target_id"),
        Index("idx_score_scorer", "scorer"),
        Index("idx_score_dimension", "dimension"),
        Index("idx_score_branch", "branch_name"),
        Index("idx_score_created", "created_at"),
    )
