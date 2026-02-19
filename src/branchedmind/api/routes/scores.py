"""REST API routes for scoring."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import ConversationNotFoundError
from branchedmind.core.scoring_engine import ScoringEngine
from branchedmind.db.engine import get_session

router = APIRouter()


class ScoreCreate(BaseModel):
    target_type: str
    target_id: str
    scorer: str
    dimension: str
    value: float
    explanation: str | None = None
    metadata: dict | None = None
    branch: str = "main"
    session_id: str | None = None


class EvaluateRequest(BaseModel):
    dimensions: list[str] | None = None


@router.post("/scores")
async def create_score(
    body: ScoreCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a score (human annotation or external scorer)."""
    engine = ScoringEngine(session)
    return await engine.create_score(
        target_type=body.target_type,
        target_id=body.target_id,
        scorer=body.scorer,
        dimension=body.dimension,
        value=body.value,
        explanation=body.explanation,
        metadata=body.metadata,
        branch_name=body.branch,
        session_id=body.session_id,
    )


@router.get("/scores")
async def list_scores(
    target_type: str | None = None,
    target_id: str | None = None,
    dimension: str | None = None,
    scorer: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """List scores with filters."""
    engine = ScoringEngine(session)
    scores = await engine.list_scores(
        target_type=target_type,
        target_id=target_id,
        dimension=dimension,
        scorer=scorer,
        limit=limit,
    )
    return {"scores": scores, "count": len(scores)}


@router.post("/conversations/{conversation_id}/evaluate")
async def evaluate_conversation(
    conversation_id: str,
    body: EvaluateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Evaluate a conversation using LLM-as-judge."""
    engine = ScoringEngine(session)
    try:
        scores = await engine.score_conversation(
            conversation_id=conversation_id,
            dimensions=body.dimensions,
        )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"scores": scores, "count": len(scores)}


@router.get("/scores/summary/{target_type}/{target_id}")
async def score_summary(
    target_type: str,
    target_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get aggregate score summary for a target."""
    engine = ScoringEngine(session)
    return await engine.get_score_summary(target_type, target_id)
