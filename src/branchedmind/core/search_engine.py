"""Search engine: hybrid BM25 + vector search."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.embedding import (
    EmbeddingProvider,
    bytes_to_embedding,
    cosine_similarity,
    get_embedding_provider,
)
from branchedmind.db.models import Fact, Observation


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
    ) -> list[dict]:
        """Search facts using hybrid BM25 + vector search.

        Args:
            query: Natural language search query.
            search_type: "hybrid", "vector", or "keyword".
            branch_name: Branch to search.
            category: Filter by category.
            limit: Max results.
            time_range: Optional {"after": ISO, "before": ISO}.

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

        # Sort by score descending and limit
        sorted_results = sorted(
            results.values(), key=lambda x: x["score"], reverse=True
        )
        return sorted_results[:limit]

    async def _keyword_search(
        self,
        query: str,
        branch_name: str,
        category: str | None,
        limit: int,
        time_range: dict | None,
    ) -> list[dict]:
        """BM25 search using SQLite FTS5."""
        if not query.strip():
            # Empty query: return recent facts
            return await self._recent_facts(branch_name, category, limit)

        # FTS5 query
        fts_result = await self._session.execute(
            text(
                "SELECT id, rank FROM facts_fts WHERE facts_fts MATCH :query "
                "ORDER BY rank LIMIT :limit"
            ),
            {"query": query, "limit": limit},
        )
        fts_rows = fts_result.fetchall()
        if not fts_rows:
            return []

        fts_ids = [row[0] for row in fts_rows]
        fts_scores = {row[0]: -row[1] for row in fts_rows}  # FTS5 rank is negative

        # Fetch full facts
        stmt = select(Fact).where(
            Fact.id.in_(fts_ids),
            Fact.branch_name == branch_name,
            Fact.status == "active",
        )
        if category:
            stmt = stmt.where(Fact.category == category)
        if time_range:
            if time_range.get("after"):
                stmt = stmt.where(Fact.created_at >= time_range["after"])
            if time_range.get("before"):
                stmt = stmt.where(Fact.created_at <= time_range["before"])

        result = await self._session.execute(stmt)
        facts = result.scalars().all()

        # Normalize scores
        max_score = max(fts_scores.values()) if fts_scores else 1.0
        return [
            self._fact_to_result(f, fts_scores.get(f.id, 0) / max(max_score, 1e-6))
            for f in facts
        ]

    async def _vector_search(
        self,
        query: str,
        branch_name: str,
        category: str | None,
        limit: int,
        time_range: dict | None,
    ) -> list[dict]:
        """Vector similarity search."""
        query_embedding = await self._embedder.embed(query)

        # Fetch all active facts on branch (for SQLite; MatrixOne would use HNSW)
        stmt = select(Fact).where(
            Fact.branch_name == branch_name,
            Fact.status == "active",
            Fact.embedding_blob.isnot(None),
        )
        if category:
            stmt = stmt.where(Fact.category == category)
        if time_range:
            if time_range.get("after"):
                stmt = stmt.where(Fact.created_at >= time_range["after"])
            if time_range.get("before"):
                stmt = stmt.where(Fact.created_at <= time_range["before"])

        result = await self._session.execute(stmt)
        facts = result.scalars().all()

        # Compute cosine similarity
        scored: list[tuple[Fact, float]] = []
        for fact in facts:
            if fact.embedding_blob:
                fact_embedding = bytes_to_embedding(fact.embedding_blob)
                sim = cosine_similarity(query_embedding, fact_embedding)
                scored.append((fact, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            self._fact_to_result(f, score) for f, score in scored[:limit]
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
        """Search observations via FTS5."""
        if not query.strip():
            return []

        fts_result = await self._session.execute(
            text(
                "SELECT id, rank FROM observations_fts "
                "WHERE observations_fts MATCH :query "
                "ORDER BY rank LIMIT :limit"
            ),
            {"query": query, "limit": limit},
        )
        fts_rows = fts_result.fetchall()
        if not fts_rows:
            return []

        fts_ids = [row[0] for row in fts_rows]
        stmt = select(Observation).where(
            Observation.id.in_(fts_ids),
            Observation.branch_name == branch_name,
        )
        if session_id:
            stmt = stmt.where(Observation.session_id == session_id)

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
            "score": score,
            "created_at": fact.created_at.isoformat() if fact.created_at else None,
            "metadata": fact.metadata_json,
        }
