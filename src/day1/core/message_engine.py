"""Message engine: CRUD and search for conversation messages."""

from __future__ import annotations

import logging

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.embedding import (
    EmbeddingProvider,
    embedding_to_vecf32,
    get_embedding_provider,
)
from day1.core.exceptions import MessageNotFoundError
from day1.db.models import Conversation, Message

logger = logging.getLogger(__name__)


class MessageEngine:
    """Manages message lifecycle: write, read, list, search."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder or get_embedding_provider()

    async def write_message(
        self,
        conversation_id: str,
        role: str,
        content: str | None = None,
        thinking: str | None = None,
        tool_calls: list[dict] | None = None,
        token_count: int = 0,
        model: str | None = None,
        parent_message_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        branch_name: str = "main",
        metadata: dict | None = None,
        embed: bool = True,
    ) -> Message:
        """Write a message to a conversation.

        Args:
            conversation_id: Parent conversation ID.
            role: Message role (user, assistant, system, tool_call, tool_result).
            content: Message text content.
            thinking: Reasoning trace (separate for privacy).
            tool_calls: List of {name, input, output} dicts.
            token_count: Token count for this message.
            model: Model that produced this message.
            parent_message_id: For threading / forking.
            session_id: Session context.
            agent_id: Agent context.
            branch_name: Target branch.
            metadata: Additional metadata.
            embed: Whether to generate embedding (default True).

        Returns:
            Created Message object.
        """
        # Get next sequence number for this conversation
        seq_result = await self._session.execute(
            select(Message.sequence_num)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_num.desc())
            .limit(1)
        )
        last_seq = seq_result.scalar_one_or_none()
        next_seq = (last_seq or 0) + 1

        # Generate embedding from content (non-fatal: capture always succeeds)
        embedding_str = None
        if embed and content:
            try:
                embed_text = content[:2000]  # Truncate for embedding
                vec = await self._embedder.embed(embed_text)
                embedding_str = embedding_to_vecf32(vec)
            except Exception as e:
                logger.warning("Embedding failed for message, saving without: %s", e)

        msg = Message(
            conversation_id=conversation_id,
            session_id=session_id,
            agent_id=agent_id,
            role=role,
            content=content,
            thinking=thinking,
            tool_calls_json=tool_calls,
            token_count=token_count,
            model=model,
            parent_message_id=parent_message_id,
            sequence_num=next_seq,
            embedding=embedding_str,
            branch_name=branch_name,
            metadata_json=metadata,
        )
        self._session.add(msg)
        await self._session.commit()
        await self._session.refresh(msg)

        # Update conversation message count and total tokens
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                message_count=Conversation.message_count + 1,
                total_tokens=Conversation.total_tokens + token_count,
            )
        )
        await self._session.commit()

        return msg

    async def get_message(self, message_id: str) -> Message:
        """Get a single message by ID."""
        result = await self._session.execute(
            select(Message).where(Message.id == message_id)
        )
        msg = result.scalar_one_or_none()
        if msg is None:
            raise MessageNotFoundError(f"Message {message_id} not found")
        return msg

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
        role: str | None = None,
    ) -> list[Message]:
        """List messages in a conversation, ordered by sequence."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_num.asc())
            .limit(limit)
            .offset(offset)
        )
        if role:
            stmt = stmt.where(Message.role == role)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_messages(
        self,
        query: str,
        branch_name: str = "main",
        conversation_id: str | None = None,
        session_id: str | None = None,
        role: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Hybrid search across messages (vector + keyword)."""
        if not query.strip():
            return []

        results: dict[str, dict] = {}

        # Keyword search via LIKE (safe fallback for MO)
        keyword_results = await self._keyword_search(
            query, branch_name, conversation_id, session_id, role, limit * 2
        )
        for r in keyword_results:
            results[r["id"]] = r

        # Vector search
        vector_results = await self._vector_search(
            query, branch_name, conversation_id, session_id, role, limit * 2
        )
        for r in vector_results:
            if r["id"] in results:
                results[r["id"]]["score"] = (
                    results[r["id"]]["score"] * 0.3 + r["score"] * 0.7
                )
            else:
                results[r["id"]] = r

        sorted_results = sorted(
            results.values(), key=lambda x: x["score"], reverse=True
        )
        return sorted_results[:limit]

    async def _keyword_search(
        self,
        query: str,
        branch_name: str,
        conversation_id: str | None,
        session_id: str | None,
        role: str | None,
        limit: int,
    ) -> list[dict]:
        """Keyword search using LIKE."""
        words = [w for w in query.strip().split() if w]
        if not words:
            return []

        where_parts = ["branch_name = :branch"]
        params: dict = {"branch": branch_name, "limit": limit}

        like_conditions = " OR ".join(
            [f"content LIKE :word{i}" for i in range(len(words))]
        )
        where_parts.append(f"({like_conditions})")
        for i, word in enumerate(words):
            params[f"word{i}"] = f"%{word}%"

        if conversation_id:
            where_parts.append("conversation_id = :conv_id")
            params["conv_id"] = conversation_id
        if session_id:
            where_parts.append("session_id = :session_id")
            params["session_id"] = session_id
        if role:
            where_parts.append("role = :role")
            params["role"] = role

        where_sql = " AND ".join(where_parts)

        stmt = (
            select(Message)
            .where(text(where_sql))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt, params)
        messages = result.scalars().all()

        results = []
        for m in messages:
            score = 0.0
            content_lower = (m.content or "").lower()
            for word in words:
                if word.lower() in content_lower:
                    score += 1.0
            score = score / len(words)
            results.append(self._message_to_result(m, score))

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    async def _vector_search(
        self,
        query: str,
        branch_name: str,
        conversation_id: str | None,
        session_id: str | None,
        role: str | None,
        limit: int,
    ) -> list[dict]:
        """Vector similarity search on message embeddings."""
        query_embedding = await self._embedder.embed(query)
        vec_str = embedding_to_vecf32(query_embedding)

        where_parts = [
            "branch_name = :branch",
            "embedding IS NOT NULL",
        ]
        params: dict = {"branch": branch_name, "limit": limit}

        if conversation_id:
            where_parts.append("conversation_id = :conv_id")
            params["conv_id"] = conversation_id
        if session_id:
            where_parts.append("session_id = :session_id")
            params["session_id"] = session_id
        if role:
            where_parts.append("role = :role")
            params["role"] = role

        where_sql = " AND ".join(where_parts)

        sql = (
            f"SELECT id, cosine_similarity(embedding, '{vec_str}') AS score "
            f"FROM messages WHERE {where_sql} "
            f"ORDER BY score DESC LIMIT :limit"
        )
        result = await self._session.execute(text(sql), params)
        rows = result.fetchall()

        if not rows:
            return []

        msg_ids = [row[0] for row in rows]
        scores = {row[0]: float(row[1]) for row in rows}

        stmt = select(Message).where(Message.id.in_(msg_ids))
        msg_result = await self._session.execute(stmt)
        messages = {m.id: m for m in msg_result.scalars().all()}

        return [
            self._message_to_result(messages[mid], scores[mid])
            for mid in msg_ids
            if mid in messages
        ]

    @staticmethod
    def _message_to_result(msg: Message, score: float) -> dict:
        """Convert a Message model to a search result dict."""
        return {
            "id": msg.id,
            "type": "message",
            "conversation_id": msg.conversation_id,
            "role": msg.role,
            "content": (msg.content or "")[:500],
            "thinking": (msg.thinking or "")[:200] if msg.thinking else None,
            "tool_calls": msg.tool_calls_json,
            "session_id": msg.session_id,
            "agent_id": msg.agent_id,
            "branch_name": msg.branch_name,
            "sequence_num": msg.sequence_num,
            "score": score,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
