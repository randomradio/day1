"""Search engine: hybrid BM25 + vector search with temporal scoring (MatrixOne)."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.embedding import (
    EmbeddingProvider,
    embedding_to_vecf32,
    get_embedding_provider,
)
from branchedmind.db.models import Fact, Observation

logger = logging.getLogger(__name__)


class SearchEngine:
    """Hybrid BM25 + Vector search over facts and observations."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder or get_embedding_provider()

    async def search(
        self,
        query: str,
        search_type: str = "hybrid",
        branch_name: str = "main",
        category: str | None = None,
        limit: int = 10,
        time_range: dict | None = None,
        temporal_weight: float = 0.0,
    ) -> list[dict]:
        """Search facts using hybrid BM25 + vector search.

        Args:
            query: Natural language search query.
            search_type: "hybrid", "vector", or "keyword".
            branch_name: Branch to search.
            category: Filter by category.
            limit: Max results.
            time_range: Optional {"after": ISO, "before": ISO}.
            temporal_weight: Weight for recency scoring (0.0-1.0).

        Returns:
            List of scored results with fact data.
        """
        results: dict[str, dict] = {}

        if search_type in ("keyword", "hybrid"):
            keyword_results = await self._keyword_search(
                query, branch_name, category, limit * 2, time_range
            )
            for r in keyword_results:
                results[r["id"]] = r

        if search_type in ("vector", "hybrid"):
            vector_results = await self._vector_search(
                query, branch_name, category, limit * 2, time_range
            )
            for r in vector_results:
                if r["id"] in results:
                    # Combine scores: weighted sum
                    results[r["id"]]["score"] = (
                        results[r["id"]]["score"] * 0.3 + r["score"] * 0.7
                    )
                else:
                    results[r["id"]] = r

        # Apply temporal scoring if enabled
        if temporal_weight > 0:
            now = datetime.now(UTC)
            for r in results.values():
                relevance = r["score"]
                recency = _recency_score(r.get("created_at"), now)
                r["score"] = (
                    relevance * (1 - temporal_weight) + recency * temporal_weight
                )

        # Sort by score descending and limit
        sorted_results = sorted(
            results.values(), key=lambda x: x["score"], reverse=True
        )
        return sorted_results[:limit]

    async def search_cross_branch(
        self,
        query: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search across branches using MATCH AGAINST with LIKE fallback.

        Args:
            query: Search query.
            task_id: Filter by task.
            agent_id: Filter by agent.
            tags: Filter facts whose task has these tags.
            limit: Max results.

        Returns:
            List of scored results with branch attribution.
        """
        if not query.strip():
            return []

        # Try MATCH AGAINST first, fall back to LIKE on error
        try:
            # MO FULLTEXT search (branch-agnostic)
            fts_result = await self._session.execute(
                text(
                    "SELECT id, MATCH(fact_text, category) AGAINST(:query IN NATURAL LANGUAGE MODE) AS score "
                    "FROM facts WHERE MATCH(fact_text, category) AGAINST(:query IN NATURAL LANGUAGE MODE) "
                    "ORDER BY score DESC LIMIT :limit"
                ),
                {"query": query, "limit": limit * 3},
            )
            fts_rows = fts_result.fetchall()
            if not fts_rows:
                return []

            fts_ids = [row[0] for row in fts_rows]
            fts_scores = {row[0]: float(row[1]) for row in fts_rows}
        except OperationalError as e:
            if "MATCH" in str(e) or "not supported" in str(e):
                logger.debug("MATCH AGAINST not supported for cross-branch, falling back to LIKE")
                # Fallback: use LIKE to get matching fact IDs
                words = [w for w in query.strip().split() if w]
                if not words:
                    return []
                like_conditions = " OR ".join(
                    [f"fact_text LIKE :word{i}" for i in range(len(words))]
                )
                like_params = {f"word{i}": f"%{w}%" for i, w in enumerate(words)}
                like_params["limit"] = limit * 3

                fts_result = await self._session.execute(
                    text(
                        f"SELECT id FROM facts WHERE ({like_conditions}) "
                        "AND status = 'active' LIMIT :limit"
                    ),
                    like_params,
                )
                fts_rows = fts_result.fetchall()
                if not fts_rows:
                    return []

                fts_ids = [row[0] for row in fts_rows]
                # Score based on word count
                fts_scores = {fid: 1.0 for fid in fts_ids}  # Uniform score for LIKE fallback
            else:
                raise

        # Fetch facts with dimension filters
        stmt = select(Fact).where(
            Fact.id.in_(fts_ids),
            Fact.status == "active",
        )
        if task_id:
            stmt = stmt.where(Fact.task_id == task_id)
        if agent_id:
            stmt = stmt.where(Fact.agent_id == agent_id)

        result = await self._session.execute(stmt)
        facts = result.scalars().all()

        max_score = max(fts_scores.values()) if fts_scores else 1.0
        results = [
            self._fact_to_result(f, fts_scores.get(f.id, 0) / max(max_score, 1e-6))
            for f in facts
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def _keyword_search(
        self,
        query: str,
        branch_name: str,
        category: str | None,
        limit: int,
        time_range: dict | None,
    ) -> list[dict]:
        """BM25 search using MatrixOne FULLTEXT INDEX + MATCH AGAINST.

        Falls back to LIKE query if MATCH AGAINST is not supported.
        """
        if not query.strip():
            # Empty query: return recent facts
            return await self._recent_facts(branch_name, category, limit)

        # Try MATCH AGAINST first, fall back to LIKE on error
        try:
            return await self._match_against_search(
                query, branch_name, category, limit, time_range
            )
        except OperationalError as e:
            if "MATCH" in str(e) or "not supported" in str(e):
                logger.debug("MATCH AGAINST not supported, falling back to LIKE search")
                return await self._like_search(
                    query, branch_name, category, limit, time_range
                )
            raise

    async def _match_against_search(
        self,
        query: str,
        branch_name: str,
        category: str | None,
        limit: int,
        time_range: dict | None,
    ) -> list[dict]:
        """BM25 search using MATCH AGAINST."""
        where_parts = [
            "MATCH(fact_text, category) AGAINST(:query IN NATURAL LANGUAGE MODE)",
            "branch_name = :branch",
            "status = 'active'",
        ]
        params: dict = {"query": query, "branch": branch_name, "limit": limit}

        if category:
            where_parts.append("category = :category")
            params["category"] = category
        if time_range:
            if time_range.get("after"):
                where_parts.append("created_at >= :after")
                params["after"] = time_range["after"]
            if time_range.get("before"):
                where_parts.append("created_at <= :before")
                params["before"] = time_range["before"]

        where_sql = " AND ".join(where_parts)

        fts_result = await self._session.execute(
            text(
                f"SELECT id, MATCH(fact_text, category) AGAINST(:query IN NATURAL LANGUAGE MODE) AS score "
                f"FROM facts WHERE {where_sql} "
                f"ORDER BY score DESC LIMIT :limit"
            ),
            params,
        )
        fts_rows = fts_result.fetchall()
        if not fts_rows:
            return []

        fts_ids = [row[0] for row in fts_rows]
        fts_scores = {row[0]: float(row[1]) for row in fts_rows}

        # Fetch full facts
        stmt = select(Fact).where(Fact.id.in_(fts_ids))
        result = await self._session.execute(stmt)
        facts = result.scalars().all()

        # Normalize scores
        max_score = max(fts_scores.values()) if fts_scores else 1.0
        return [
            self._fact_to_result(f, fts_scores.get(f.id, 0) / max(max_score, 1e-6))
            for f in facts
        ]

    async def _like_search(
        self,
        query: str,
        branch_name: str,
        category: str | None,
        limit: int,
        time_range: dict | None,
    ) -> list[dict]:
        """Fallback keyword search using LIKE."""
        # Split query into words and create LIKE conditions
        words = [w for w in query.strip().split() if w]
        if not words:
            return await self._recent_facts(branch_name, category, limit)

        where_parts = ["branch_name = :branch", "status = 'active'"]
        params: dict = {"branch": branch_name, "limit": limit}

        # Add LIKE condition for each word - matches any word in fact_text
        like_conditions = " OR ".join(
            [f"fact_text LIKE :word{i}" for i in range(len(words))]
        )
        where_parts.append(f"({like_conditions})")
        for i, word in enumerate(words):
            params[f"word{i}"] = f"%{word}%"

        if category:
            where_parts.append("category = :category")
            params["category"] = category
        if time_range:
            if time_range.get("after"):
                where_parts.append("created_at >= :after")
                params["after"] = time_range["after"]
            if time_range.get("before"):
                where_parts.append("created_at <= :before")
                params["before"] = time_range["before"]

        where_sql = " AND ".join(where_parts)

        # Use ORM query for LIKE search (simpler than raw SQL)
        stmt = (
            select(Fact)
            .where(text(where_sql))
            .order_by(Fact.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt, params)
        facts = result.scalars().all()

        # Score based on word matches (more matches = higher score)
        results = []
        for f in facts:
            score = 0.0
            fact_lower = f.fact_text.lower()
            for word in words:
                if word.lower() in fact_lower:
                    score += 1.0
            # Normalize by number of words
            score = score / len(words)
            results.append(self._fact_to_result(f, score))

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def _vector_search(
        self,
        query: str,
        branch_name: str,
        category: str | None,
        limit: int,
        time_range: dict | None,
    ) -> list[dict]:
        """Vector similarity search using MO SQL cosine_similarity()."""
        query_embedding = await self._embedder.embed(query)
        vec_str = embedding_to_vecf32(query_embedding)

        where_parts = [
            "branch_name = :branch",
            "status = 'active'",
            "embedding IS NOT NULL",
        ]
        params: dict = {"branch": branch_name, "limit": limit}

        if category:
            where_parts.append("category = :category")
            params["category"] = category
        if time_range:
            if time_range.get("after"):
                where_parts.append("created_at >= :after")
                params["after"] = time_range["after"]
            if time_range.get("before"):
                where_parts.append("created_at <= :before")
                params["before"] = time_range["before"]

        where_sql = " AND ".join(where_parts)

        # MO cosine_similarity — vec_str inlined (not a bind param) since MO
        # expects a vecf32 literal for the function argument
        sql = (
            f"SELECT id, cosine_similarity(embedding, '{vec_str}') AS score "
            f"FROM facts WHERE {where_sql} "
            f"ORDER BY score DESC LIMIT :limit"
        )
        result = await self._session.execute(text(sql), params)
        rows = result.fetchall()

        if not rows:
            return []

        fact_ids = [row[0] for row in rows]
        scores = {row[0]: float(row[1]) for row in rows}

        # Fetch full Fact objects
        stmt = select(Fact).where(Fact.id.in_(fact_ids))
        fact_result = await self._session.execute(stmt)
        facts = {f.id: f for f in fact_result.scalars().all()}

        return [
            self._fact_to_result(facts[fid], scores[fid])
            for fid in fact_ids
            if fid in facts
        ]

    async def _recent_facts(
        self, branch_name: str, category: str | None, limit: int
    ) -> list[dict]:
        """Return most recent facts (for empty queries)."""
        stmt = (
            select(Fact)
            .where(Fact.branch_name == branch_name, Fact.status == "active")
            .order_by(Fact.created_at.desc())
            .limit(limit)
        )
        if category:
            stmt = stmt.where(Fact.category == category)
        result = await self._session.execute(stmt)
        facts = result.scalars().all()
        return [self._fact_to_result(f, 1.0) for f in facts]

    async def search_observations(
        self,
        query: str,
        branch_name: str = "main",
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search observations via MO MATCH AGAINST with LIKE fallback."""
        if not query.strip():
            return []

        # Try MATCH AGAINST first, fall back to LIKE on error
        try:
            return await self._match_against_search_observations(
                query, branch_name, session_id, limit
            )
        except OperationalError as e:
            if "MATCH" in str(e) or "not supported" in str(e):
                logger.debug("MATCH AGAINST not supported for observations, falling back to LIKE")
                return await self._like_search_observations(
                    query, branch_name, session_id, limit
                )
            raise

    async def _match_against_search_observations(
        self,
        query: str,
        branch_name: str,
        session_id: str | None,
        limit: int,
    ) -> list[dict]:
        """Search observations via MATCH AGAINST."""
        where_parts = [
            "MATCH(summary, tool_name) AGAINST(:query IN NATURAL LANGUAGE MODE)",
            "branch_name = :branch",
        ]
        params: dict = {"query": query, "branch": branch_name, "limit": limit}

        if session_id:
            where_parts.append("session_id = :session_id")
            params["session_id"] = session_id

        where_sql = " AND ".join(where_parts)

        fts_result = await self._session.execute(
            text(f"SELECT id FROM observations WHERE {where_sql} " f"LIMIT :limit"),
            params,
        )
        fts_rows = fts_result.fetchall()
        if not fts_rows:
            return []

        fts_ids = [row[0] for row in fts_rows]
        stmt = select(Observation).where(Observation.id.in_(fts_ids))
        result = await self._session.execute(stmt)
        observations = result.scalars().all()

        return [
            {
                "id": o.id,
                "type": "observation",
                "observation_type": o.observation_type,
                "tool_name": o.tool_name,
                "summary": o.summary,
                "session_id": o.session_id,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in observations
        ]

    async def _like_search_observations(
        self,
        query: str,
        branch_name: str,
        session_id: str | None,
        limit: int,
    ) -> list[dict]:
        """Search observations via LIKE (fallback)."""
        words = [w for w in query.strip().split() if w]
        if not words:
            return []

        where_parts = ["branch_name = :branch"]
        params: dict = {"branch": branch_name, "limit": limit}

        # Add LIKE condition for each word
        like_conditions = " OR ".join(
            [f"summary LIKE :word{i}" for i in range(len(words))]
        )
        where_parts.append(f"({like_conditions})")
        for i, word in enumerate(words):
            params[f"word{i}"] = f"%{word}%"

        if session_id:
            where_parts.append("session_id = :session_id")
            params["session_id"] = session_id

        where_sql = " AND ".join(where_parts)

        stmt = (
            select(Observation)
            .where(text(where_sql))
            .order_by(Observation.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt, params)
        observations = result.scalars().all()

        return [
            {
                "id": o.id,
                "type": "observation",
                "observation_type": o.observation_type,
                "tool_name": o.tool_name,
                "summary": o.summary,
                "session_id": o.session_id,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in observations
        ]

    @staticmethod
    def _fact_to_result(fact: Fact, score: float) -> dict:
        """Convert a Fact model to a search result dict."""
        return {
            "id": fact.id,
            "type": "fact",
            "fact_text": fact.fact_text,
            "category": fact.category,
            "confidence": fact.confidence,
            "status": fact.status,
            "branch_name": fact.branch_name,
            "session_id": fact.session_id,
            "task_id": fact.task_id,
            "agent_id": fact.agent_id,
            "score": score,
            "created_at": fact.created_at.isoformat() if fact.created_at else None,
            "metadata": fact.metadata_json,
        }


def _recency_score(created_at_iso: str | None, now: datetime) -> float:
    """Compute recency score with exponential decay.

    Returns value between 0.0 and 1.0, where 1.0 is "just created".
    Decay rate: half-life of ~6 days (0.005 per hour).
    """
    if not created_at_iso:
        return 0.5
    try:
        created = datetime.fromisoformat(created_at_iso)
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        hours_old = max((now - created).total_seconds() / 3600, 0)
        return math.exp(-0.005 * hours_old)
    except (ValueError, TypeError):
        return 0.5
