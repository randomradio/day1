"""Analytics engine: aggregate metrics across sessions, conversations, agents."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from day1.db.models import (
    Conversation,
    ConsolidationHistory,
    Fact,
    Message,
    Observation,
    Session,
    Task,
    TaskAgent,
)

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """Compute aggregate metrics across the Day1 data model."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(
        self,
        branch_name: str | None = None,
        days: int = 30,
    ) -> dict:
        """Top-level dashboard metrics.

        Args:
            branch_name: Filter to a specific branch (None = all).
            days: Lookback window in days.

        Returns:
            Dict with counts, totals, and recent activity.
        """
        since = datetime.utcnow() - timedelta(days=days)

        counts = await self._get_counts(branch_name, since)
        token_stats = await self._get_token_stats(branch_name, since)
        activity = await self._get_recent_activity(branch_name, since)
        consolidation = await self._get_consolidation_stats(branch_name, since)

        return {
            "period_days": days,
            "branch_name": branch_name or "all",
            "counts": counts,
            "tokens": token_stats,
            "activity": activity,
            "consolidation": consolidation,
        }

    async def session_analytics(self, session_id: str) -> dict:
        """Per-session breakdown.

        Args:
            session_id: The session to analyze.

        Returns:
            Dict with session metadata and per-conversation stats.
        """
        # Session info
        sess_result = await self._session.execute(
            select(Session).where(Session.session_id == session_id)
        )
        # Conversations in this session
        conv_result = await self._session.execute(
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.asc())
        )
        conversations = list(conv_result.scalars().all())
        sess = sess_result.scalar_one_or_none()
        if sess is None and not conversations:
            return {"error": f"Session {session_id} not found"}

        # Facts created during this session
        fact_count_result = await self._session.execute(
            select(func.count(Fact.id))
            .where(Fact.session_id == session_id)
        )
        fact_count = fact_count_result.scalar() or 0

        # Observations during this session
        obs_count_result = await self._session.execute(
            select(func.count(Observation.id))
            .where(Observation.session_id == session_id)
        )
        obs_count = obs_count_result.scalar() or 0

        # Tool call breakdown
        tool_result = await self._session.execute(
            select(Observation.tool_name, func.count(Observation.id))
            .where(
                Observation.session_id == session_id,
                Observation.tool_name.isnot(None),
            )
            .group_by(Observation.tool_name)
            .order_by(func.count(Observation.id).desc())
        )
        tool_breakdown = [
            {"tool": row[0], "count": row[1]}
            for row in tool_result.fetchall()
        ]

        # Message role breakdown
        msg_result = await self._session.execute(
            select(Message.role, func.count(Message.id))
            .where(Message.session_id == session_id)
            .group_by(Message.role)
        )
        role_breakdown = {row[0]: row[1] for row in msg_result.fetchall()}

        total_messages = sum(c.message_count for c in conversations)
        total_tokens = sum(c.total_tokens for c in conversations)

        return {
            "session_id": session_id,
            "status": sess.status if sess else "unknown",
            "branch_name": (
                sess.branch_name if sess else (
                    conversations[0].branch_name if conversations else "main"
                )
            ),
            "started_at": (
                sess.started_at.isoformat() if sess and sess.started_at else None
            ),
            "ended_at": (
                sess.ended_at.isoformat() if sess and sess.ended_at else None
            ),
            "conversations": len(conversations),
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "facts_created": fact_count,
            "observations": obs_count,
            "tool_breakdown": tool_breakdown,
            "message_roles": role_breakdown,
            "conversation_details": [
                {
                    "id": c.id,
                    "title": c.title,
                    "status": c.status,
                    "message_count": c.message_count,
                    "total_tokens": c.total_tokens,
                    "is_fork": c.parent_conversation_id is not None,
                    "created_at": (
                        c.created_at.isoformat() if c.created_at else None
                    ),
                }
                for c in conversations
            ],
        }

    async def agent_analytics(
        self,
        agent_id: str,
        days: int = 30,
    ) -> dict:
        """Per-agent performance metrics.

        Args:
            agent_id: The agent to analyze.
            days: Lookback window.

        Returns:
            Dict with agent activity, tool usage, and output metrics.
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Sessions by this agent
        sess_result = await self._session.execute(
            select(func.count(Session.session_id))
            .where(
                Session.agent_id == agent_id,
                Session.started_at >= since,
            )
        )
        session_count = sess_result.scalar() or 0

        # Conversations by this agent
        conv_result = await self._session.execute(
            select(
                func.count(Conversation.id),
                func.coalesce(func.sum(Conversation.message_count), 0),
                func.coalesce(func.sum(Conversation.total_tokens), 0),
            )
            .where(
                Conversation.agent_id == agent_id,
                Conversation.created_at >= since,
            )
        )
        conv_row = conv_result.fetchone()
        conv_count = conv_row[0] if conv_row else 0
        msg_count = conv_row[1] if conv_row else 0
        token_count = conv_row[2] if conv_row else 0

        # Facts produced
        fact_result = await self._session.execute(
            select(
                func.count(Fact.id),
                Fact.category,
            )
            .where(
                Fact.agent_id == agent_id,
                Fact.created_at >= since,
            )
            .group_by(Fact.category)
        )
        fact_categories = {
            row[1] or "uncategorized": row[0]
            for row in fact_result.fetchall()
        }

        # Tool usage
        tool_result = await self._session.execute(
            select(
                Observation.tool_name,
                func.count(Observation.id),
                Observation.outcome,
            )
            .where(
                Observation.agent_id == agent_id,
                Observation.created_at >= since,
                Observation.tool_name.isnot(None),
            )
            .group_by(Observation.tool_name, Observation.outcome)
        )
        tool_stats: dict[str, dict] = {}
        for row in tool_result.fetchall():
            tool_name = row[0]
            count = row[1]
            outcome = row[2] or "unknown"
            if tool_name not in tool_stats:
                tool_stats[tool_name] = {"total": 0, "outcomes": {}}
            tool_stats[tool_name]["total"] += count
            tool_stats[tool_name]["outcomes"][outcome] = count

        # Task assignments
        task_result = await self._session.execute(
            select(func.count(TaskAgent.id))
            .where(TaskAgent.agent_id == agent_id)
        )
        task_count = task_result.scalar() or 0

        return {
            "agent_id": agent_id,
            "period_days": days,
            "sessions": session_count,
            "conversations": conv_count,
            "total_messages": msg_count,
            "total_tokens": token_count,
            "facts_by_category": fact_categories,
            "total_facts": sum(fact_categories.values()),
            "tool_usage": tool_stats,
            "task_assignments": task_count,
        }

    async def trends(
        self,
        branch_name: str | None = None,
        days: int = 30,
        granularity: str = "day",
    ) -> dict:
        """Time-series metrics.

        Args:
            branch_name: Filter to branch (None = all).
            days: Lookback window.
            granularity: "day" or "hour".

        Returns:
            Dict with time-bucketed counts.
        """
        since = datetime.utcnow() - timedelta(days=days)

        if granularity == "hour":
            date_fmt = "%Y-%m-%d %H:00"
            trunc_expr = "DATE_FORMAT(created_at, '%Y-%m-%d %H:00')"
        else:
            date_fmt = "%Y-%m-%d"
            trunc_expr = "DATE(created_at)"

        # Messages over time
        msg_branch_filter = (
            f"AND branch_name = :branch" if branch_name else ""
        )
        msg_sql = (
            f"SELECT {trunc_expr} AS period, COUNT(*) AS cnt "
            f"FROM messages "
            f"WHERE created_at >= :since {msg_branch_filter} "
            f"GROUP BY period ORDER BY period"
        )
        params: dict = {"since": since}
        if branch_name:
            params["branch"] = branch_name

        msg_result = await self._session.execute(text(msg_sql), params)
        message_trend = [
            {"period": str(row[0]), "count": row[1]}
            for row in msg_result.fetchall()
        ]

        # Facts over time
        fact_sql = (
            f"SELECT {trunc_expr} AS period, COUNT(*) AS cnt "
            f"FROM facts "
            f"WHERE created_at >= :since {msg_branch_filter} "
            f"GROUP BY period ORDER BY period"
        )
        fact_result = await self._session.execute(text(fact_sql), params)
        fact_trend = [
            {"period": str(row[0]), "count": row[1]}
            for row in fact_result.fetchall()
        ]

        # Conversations over time
        conv_branch_filter = (
            f"AND branch_name = :branch" if branch_name else ""
        )
        conv_sql = (
            f"SELECT {trunc_expr} AS period, COUNT(*) AS cnt "
            f"FROM conversations "
            f"WHERE created_at >= :since {conv_branch_filter} "
            f"GROUP BY period ORDER BY period"
        )
        conv_result = await self._session.execute(text(conv_sql), params)
        conv_trend = [
            {"period": str(row[0]), "count": row[1]}
            for row in conv_result.fetchall()
        ]

        return {
            "period_days": days,
            "granularity": granularity,
            "branch_name": branch_name or "all",
            "messages": message_trend,
            "facts": fact_trend,
            "conversations": conv_trend,
        }

    async def conversation_analytics(
        self,
        conversation_id: str,
    ) -> dict:
        """Detailed analytics for a single conversation.

        Args:
            conversation_id: The conversation to analyze.

        Returns:
            Dict with message stats, role distribution, token usage.
        """
        conv_result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv is None:
            return {"error": f"Conversation {conversation_id} not found"}

        # Role distribution
        role_result = await self._session.execute(
            select(Message.role, func.count(Message.id))
            .where(Message.conversation_id == conversation_id)
            .group_by(Message.role)
        )
        roles = {row[0]: row[1] for row in role_result.fetchall()}

        # Token distribution by role
        token_result = await self._session.execute(
            select(
                Message.role,
                func.coalesce(func.sum(Message.token_count), 0),
            )
            .where(Message.conversation_id == conversation_id)
            .group_by(Message.role)
        )
        tokens_by_role = {row[0]: row[1] for row in token_result.fetchall()}

        # Tool calls in this conversation
        tool_msg_result = await self._session.execute(
            select(func.count(Message.id))
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "tool_call",
            )
        )
        tool_call_count = tool_msg_result.scalar() or 0

        # Fork count
        fork_result = await self._session.execute(
            select(func.count(Conversation.id))
            .where(Conversation.parent_conversation_id == conversation_id)
        )
        fork_count = fork_result.scalar() or 0

        return {
            "conversation_id": conversation_id,
            "title": conv.title,
            "status": conv.status,
            "message_count": conv.message_count,
            "total_tokens": conv.total_tokens,
            "model": conv.model,
            "message_roles": roles,
            "tokens_by_role": tokens_by_role,
            "tool_calls": tool_call_count,
            "forks": fork_count,
            "is_fork": conv.parent_conversation_id is not None,
            "parent_conversation_id": conv.parent_conversation_id,
            "created_at": (
                conv.created_at.isoformat() if conv.created_at else None
            ),
        }

    # --- Internal helpers ---

    async def _get_counts(
        self,
        branch_name: str | None,
        since: datetime,
    ) -> dict:
        """Get entity counts."""
        counts = {}
        for model, name in [
            (Conversation, "conversations"),
            (Message, "messages"),
            (Fact, "facts"),
            (Observation, "observations"),
        ]:
            stmt = select(func.count(model.id)).where(
                model.created_at >= since
            )
            if branch_name:
                stmt = stmt.where(model.branch_name == branch_name)
            result = await self._session.execute(stmt)
            counts[name] = result.scalar() or 0

        # Sessions (different PK)
        sess_stmt = select(func.count(Session.session_id)).where(
            Session.started_at >= since
        )
        if branch_name:
            sess_stmt = sess_stmt.where(Session.branch_name == branch_name)
        sess_result = await self._session.execute(sess_stmt)
        counts["sessions"] = sess_result.scalar() or 0

        return counts

    async def _get_token_stats(
        self,
        branch_name: str | None,
        since: datetime,
    ) -> dict:
        """Get token usage stats."""
        stmt = select(
            func.coalesce(func.sum(Conversation.total_tokens), 0),
            func.coalesce(
                func.avg(Conversation.total_tokens), 0
            ),
        ).where(Conversation.created_at >= since)
        if branch_name:
            stmt = stmt.where(Conversation.branch_name == branch_name)

        result = await self._session.execute(stmt)
        row = result.fetchone()
        return {
            "total": row[0] if row else 0,
            "avg_per_conversation": round(float(row[1]), 1) if row else 0.0,
        }

    async def _get_recent_activity(
        self,
        branch_name: str | None,
        since: datetime,
    ) -> dict:
        """Get recent activity summary."""
        # Latest 5 conversations
        stmt = (
            select(Conversation)
            .where(Conversation.created_at >= since)
            .order_by(Conversation.created_at.desc())
            .limit(5)
        )
        if branch_name:
            stmt = stmt.where(Conversation.branch_name == branch_name)

        result = await self._session.execute(stmt)
        recent = [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "message_count": c.message_count,
                "created_at": (
                    c.created_at.isoformat() if c.created_at else None
                ),
            }
            for c in result.scalars().all()
        ]
        return {"recent_conversations": recent}

    async def _get_consolidation_stats(
        self,
        branch_name: str | None,
        since: datetime,
    ) -> dict:
        """Get consolidation yield stats."""
        stmt = select(
            func.coalesce(func.sum(ConsolidationHistory.facts_created), 0),
            func.coalesce(func.sum(ConsolidationHistory.facts_updated), 0),
            func.coalesce(
                func.sum(ConsolidationHistory.facts_deduplicated), 0
            ),
            func.coalesce(
                func.sum(ConsolidationHistory.observations_processed), 0
            ),
        ).where(ConsolidationHistory.created_at >= since)
        if branch_name:
            stmt = stmt.where(
                ConsolidationHistory.source_branch == branch_name
            )

        result = await self._session.execute(stmt)
        row = result.fetchone()

        obs_processed = row[3] if row else 0
        facts_created = row[0] if row else 0
        yield_rate = (
            round(facts_created / obs_processed, 3) if obs_processed else 0.0
        )

        return {
            "facts_created": facts_created,
            "facts_updated": row[1] if row else 0,
            "facts_deduplicated": row[2] if row else 0,
            "observations_processed": obs_processed,
            "yield_rate": yield_rate,
        }
