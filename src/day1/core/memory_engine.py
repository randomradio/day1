"""MemoryEngine — single engine for write, search, branch, and snapshot ops."""

from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.embedding import EmbeddingProvider, embedding_to_vecf32, get_embedding_provider
from day1.db.models import Branch, Memory, Snapshot

logger = logging.getLogger(__name__)


class MemoryEngine:
    def __init__(self, session: AsyncSession, embedder: EmbeddingProvider | None = None) -> None:
        self._session = session
        self._embedder = embedder or get_embedding_provider()

    # ── Write ────────────────────────────────────────────────────────────────

    async def write(
        self,
        text: str,
        context: str | None = None,
        file_context: str | None = None,
        session_id: str | None = None,
        branch_name: str = "main",
    ) -> Memory:
        """Store a memory with NL text + optional context (WHY/HOW) and file path."""
        embedding_vec = await self._embedder.embed(text)
        vec_str = embedding_to_vecf32(embedding_vec)

        mem = Memory(
            text=text,
            context=context,
            file_context=file_context,
            session_id=session_id,
            branch_name=branch_name,
            embedding=vec_str,
        )
        self._session.add(mem)
        await self._session.commit()
        await self._session.refresh(mem)
        return mem

    # ── Search ───────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        file_context: str | None = None,
        branch_name: str = "main",
        limit: int = 10,
    ) -> list[dict]:
        """Hybrid search: vector + keyword (MATCH AGAINST / LIKE fallback)."""
        results: dict[str, dict] = {}

        keyword_hits = await self._keyword_search(query, branch_name, file_context, limit * 2)
        for r in keyword_hits:
            results[r["id"]] = r

        vector_hits = await self._vector_search(query, branch_name, file_context, limit * 2)
        for r in vector_hits:
            if r["id"] in results:
                results[r["id"]]["score"] = results[r["id"]]["score"] * 0.3 + r["score"] * 0.7
            else:
                results[r["id"]] = r

        sorted_results = sorted(results.values(), key=lambda x: x["score"], reverse=True)
        return sorted_results[:limit]

    async def _keyword_search(
        self, query: str, branch_name: str, file_context: str | None, limit: int
    ) -> list[dict]:
        if not query.strip():
            return await self._recent_memories(branch_name, file_context, limit)
        try:
            return await self._match_against(query, branch_name, file_context, limit)
        except OperationalError as e:
            if "MATCH" in str(e) or "not supported" in str(e):
                logger.debug("MATCH AGAINST not supported, falling back to LIKE")
                return await self._like_search(query, branch_name, file_context, limit)
            raise

    async def _match_against(
        self, query: str, branch_name: str, file_context: str | None, limit: int
    ) -> list[dict]:
        where = ["MATCH(text, context) AGAINST(:q IN NATURAL LANGUAGE MODE)", "branch_name = :branch"]
        params: dict = {"q": query, "branch": branch_name, "limit": limit}
        if file_context:
            where.append("file_context = :fc")
            params["fc"] = file_context

        sql = (
            "SELECT id, MATCH(text, context) AGAINST(:q IN NATURAL LANGUAGE MODE) AS score "
            f"FROM memories WHERE {' AND '.join(where)} ORDER BY score DESC LIMIT :limit"
        )
        rows = (await self._session.execute(text(sql), params)).fetchall()
        if not rows:
            return []
        ids = [r[0] for r in rows]
        scores = {r[0]: float(r[1]) for r in rows}
        mems = (await self._session.execute(select(Memory).where(Memory.id.in_(ids)))).scalars().all()
        max_s = max(scores.values()) or 1.0
        return [self._to_dict(m, scores.get(m.id, 0) / max_s) for m in mems]

    async def _like_search(
        self, query: str, branch_name: str, file_context: str | None, limit: int
    ) -> list[dict]:
        words = [w for w in query.strip().split() if w]
        if not words:
            return await self._recent_memories(branch_name, file_context, limit)

        like_parts = " OR ".join([f"text LIKE :w{i}" for i in range(len(words))])
        where = [f"({like_parts})", "branch_name = :branch"]
        params: dict = {"branch": branch_name, "limit": limit}
        for i, w in enumerate(words):
            params[f"w{i}"] = f"%{w}%"
        if file_context:
            where.append("file_context = :fc")
            params["fc"] = file_context

        stmt = (
            select(Memory)
            .where(text(" AND ".join(where)))
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        mems = (await self._session.execute(stmt, params)).scalars().all()
        results = []
        for m in mems:
            score = sum(1.0 for w in words if w.lower() in m.text.lower()) / len(words)
            results.append(self._to_dict(m, score))
        return sorted(results, key=lambda x: x["score"], reverse=True)

    async def _vector_search(
        self, query: str, branch_name: str, file_context: str | None, limit: int
    ) -> list[dict]:
        try:
            vec = await self._embedder.embed(query)
        except Exception:
            logger.debug("Embedding failed, skipping vector search")
            return []
        vec_str = embedding_to_vecf32(vec)

        where = ["branch_name = :branch", "embedding IS NOT NULL"]
        params: dict = {"branch": branch_name, "limit": limit}
        if file_context:
            where.append("file_context = :fc")
            params["fc"] = file_context

        sql = (
            f"SELECT id, cosine_similarity(embedding, '{vec_str}') AS score "
            f"FROM memories WHERE {' AND '.join(where)} ORDER BY score DESC LIMIT :limit"
        )
        try:
            rows = (await self._session.execute(text(sql), params)).fetchall()
        except OperationalError:
            logger.debug("Vector search failed, skipping")
            return []
        if not rows:
            return []
        ids = [r[0] for r in rows]
        scores = {r[0]: float(r[1]) for r in rows}
        mems = (await self._session.execute(select(Memory).where(Memory.id.in_(ids)))).scalars().all()
        mem_map = {m.id: m for m in mems}
        return [self._to_dict(mem_map[fid], scores[fid]) for fid in ids if fid in mem_map]

    async def _recent_memories(
        self, branch_name: str, file_context: str | None, limit: int
    ) -> list[dict]:
        stmt = select(Memory).where(Memory.branch_name == branch_name).order_by(Memory.created_at.desc()).limit(limit)
        if file_context:
            stmt = stmt.where(Memory.file_context == file_context)
        mems = (await self._session.execute(stmt)).scalars().all()
        return [self._to_dict(m, 1.0) for m in mems]

    # ── Branch ───────────────────────────────────────────────────────────────

    async def ensure_main_branch(self) -> None:
        result = await self._session.execute(select(Branch).where(Branch.branch_name == "main"))
        if result.scalar_one_or_none() is None:
            try:
                self._session.add(Branch(branch_name="main", description="Default memory branch"))
                await self._session.commit()
            except IntegrityError:
                await self._session.rollback()

    async def create_branch(
        self, branch_name: str, parent_branch: str = "main", description: str | None = None
    ) -> Branch:
        branch = Branch(branch_name=branch_name, parent_branch=parent_branch, description=description)
        self._session.add(branch)
        await self._session.commit()
        await self._session.refresh(branch)
        return branch

    async def get_branch(self, branch_name: str) -> Branch:
        result = await self._session.execute(select(Branch).where(Branch.branch_name == branch_name))
        branch = result.scalar_one_or_none()
        if branch is None:
            raise ValueError(f"Branch not found: {branch_name}")
        return branch

    async def list_branches(self, status: str | None = None) -> list[Branch]:
        stmt = select(Branch)
        if status:
            stmt = stmt.where(Branch.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    # ── Snapshot ─────────────────────────────────────────────────────────────

    async def create_snapshot(self, branch_name: str, label: str | None = None) -> Snapshot:
        snap = Snapshot(branch_name=branch_name, label=label)
        self._session.add(snap)
        await self._session.commit()
        await self._session.refresh(snap)
        return snap

    async def list_snapshots(self, branch_name: str | None = None) -> list[Snapshot]:
        stmt = select(Snapshot).order_by(Snapshot.created_at.desc())
        if branch_name:
            stmt = stmt.where(Snapshot.branch_name == branch_name)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_snapshot(self, snapshot_id: str) -> Snapshot:
        result = await self._session.execute(select(Snapshot).where(Snapshot.id == snapshot_id))
        snap = result.scalar_one_or_none()
        if snap is None:
            raise ValueError(f"Snapshot not found: {snapshot_id}")
        return snap

    async def restore_snapshot(self, snapshot_id: str) -> dict:
        """Return memories as they were at snapshot time (up to created_at)."""
        snap = await self.get_snapshot(snapshot_id)
        stmt = (
            select(Memory)
            .where(Memory.branch_name == snap.branch_name, Memory.created_at <= snap.created_at)
            .order_by(Memory.created_at.desc())
        )
        mems = (await self._session.execute(stmt)).scalars().all()
        return {
            "snapshot_id": snap.id,
            "label": snap.label,
            "branch_name": snap.branch_name,
            "snapshot_time": snap.created_at.isoformat() if snap.created_at else None,
            "memories": [self._to_dict(m, 1.0) for m in mems],
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(m: Memory, score: float) -> dict:
        return {
            "id": m.id,
            "text": m.text,
            "context": m.context,
            "file_context": m.file_context,
            "session_id": m.session_id,
            "branch_name": m.branch_name,
            "score": score,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
