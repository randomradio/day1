"""Verification engine: LLM-as-judge for fact and conversation verification.

Extends the ScoringEngine pattern to provide:
- Individual fact verification (accuracy, relevance, staleness)
- Batch verification across a branch
- Verification status transitions (unverified → verified | invalidated)
- Merge gate: only verified facts can be merged to parent branch
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import FactNotFoundError, VerificationError
from day1.db.models import Conversation, Fact, Message, Score

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verification dimensions for facts
# ---------------------------------------------------------------------------

FACT_VERIFICATION_DIMENSIONS = [
    "accuracy",
    "relevance",
    "specificity",
]

FACT_VERIFICATION_SYSTEM_PROMPT = """\
You are an expert knowledge verifier. You evaluate structured facts for quality \
and trustworthiness.

For each dimension, return a JSON object with:
- "value": a float from 0.0 (worst) to 1.0 (best)
- "explanation": a 1-2 sentence justification

Dimension definitions:
- accuracy: Is this fact likely to be factually correct and internally consistent?
- relevance: Is this fact useful, non-trivial knowledge worth preserving?
- specificity: Is this fact specific and actionable rather than vague or generic?
- staleness: Is this fact likely still current and not outdated? (1.0 = fresh, 0.0 = stale)

Be calibrated: 0.5 is mediocre, 0.7 is good, 0.9+ is exceptional.
"""

FACT_VERIFICATION_PROMPT = """\
Evaluate the following fact on these dimensions: {dimensions}

<fact>
Category: {category}
Confidence: {confidence}
Text: {fact_text}
</fact>

{context_section}

Return ONLY valid JSON in this exact format:
{{
  "scores": {{
    "<dimension>": {{
      "value": <float 0.0-1.0>,
      "explanation": "<1-2 sentence justification>"
    }}
  }},
  "verdict": "<verified|unverified|invalidated>",
  "reason": "<1 sentence summary of verification decision>"
}}
"""

# Thresholds for verification decisions
VERIFY_THRESHOLD = 0.6  # Avg score must be >= this to be "verified"
INVALIDATE_THRESHOLD = 0.3  # Avg score < this → "invalidated"


async def _call_fact_verifier(
    fact_text: str,
    category: str | None,
    confidence: float,
    dimensions: list[str],
    context: str | None = None,
    llm_client: object | None = None,
) -> dict:
    """Call LLM to verify a fact.

    Returns dict with scores, verdict, and reason.
    Falls back to heuristic-based verification if LLM is unavailable.
    """
    if llm_client is None:
        from day1.core.llm import get_llm_client

        llm_client = get_llm_client()

    if llm_client is None:
        logger.warning("No LLM configured — using heuristic verification")
        return _heuristic_verify(fact_text, category, confidence, dimensions)

    context_section = ""
    if context:
        context_section = f"<context>\n{context}\n</context>"

    prompt = FACT_VERIFICATION_PROMPT.format(
        dimensions=", ".join(dimensions),
        category=category or "unknown",
        confidence=confidence,
        fact_text=fact_text,
        context_section=context_section,
    )

    try:
        result = await llm_client.complete_structured(
            prompt=prompt,
            schema={
                "type": "object",
                "properties": {
                    "scores": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "number"},
                                "explanation": {"type": "string"},
                            },
                        },
                    },
                    "verdict": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
            temperature=0.2,
            system_prompt=FACT_VERIFICATION_SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.error("LLM verification call failed: %s", e)
        return _heuristic_verify(fact_text, category, confidence, dimensions)

    # Normalize scores
    scores_raw = result.get("scores", {})
    scores: dict[str, tuple[float, str]] = {}
    for dim in dimensions:
        entry = scores_raw.get(dim, {})
        value = float(entry.get("value", 0.5))
        value = max(0.0, min(1.0, value))
        explanation = entry.get("explanation", "No explanation provided")
        scores[dim] = (round(value, 3), explanation)

    verdict = result.get("verdict", "unverified")
    if verdict not in ("verified", "unverified", "invalidated"):
        verdict = "unverified"

    return {
        "scores": scores,
        "verdict": verdict,
        "reason": result.get("reason", ""),
    }


def _heuristic_verify(
    fact_text: str,
    category: str | None,
    confidence: float,
    dimensions: list[str],
) -> dict:
    """Heuristic-based verification when LLM is unavailable.

    Uses text length, category, and confidence as signals.
    """
    # Score based on fact quality signals
    text_len = len(fact_text.split())
    specificity_score = min(1.0, text_len / 20.0)  # Longer = more specific
    relevance_score = 0.7 if category in {
        "bug_fix", "architecture", "pattern", "decision", "security",
    } else 0.5
    accuracy_score = confidence  # Trust the existing confidence

    dim_scores: dict[str, tuple[float, str]] = {}
    for dim in dimensions:
        if dim == "accuracy":
            dim_scores[dim] = (round(accuracy_score, 3), "Based on existing confidence")
        elif dim == "relevance":
            dim_scores[dim] = (round(relevance_score, 3), "Based on category classification")
        elif dim == "specificity":
            dim_scores[dim] = (round(specificity_score, 3), "Based on fact length/detail")
        else:
            dim_scores[dim] = (0.5, "Heuristic — LLM scorer unavailable")

    avg_score = sum(v for v, _ in dim_scores.values()) / len(dim_scores) if dim_scores else 0.5

    if avg_score >= VERIFY_THRESHOLD:
        verdict = "verified"
    elif avg_score < INVALIDATE_THRESHOLD:
        verdict = "invalidated"
    else:
        verdict = "unverified"

    return {
        "scores": dim_scores,
        "verdict": verdict,
        "reason": f"Heuristic verification (avg={avg_score:.2f})",
    }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class VerificationEngine:
    """Verify facts and conversations using LLM-as-judge or heuristics."""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: object | None = None,
    ) -> None:
        self._session = session
        self._llm = llm_client

    async def verify_fact(
        self,
        fact_id: str,
        dimensions: list[str] | None = None,
        context: str | None = None,
    ) -> dict:
        """Verify a single fact using LLM-as-judge.

        Args:
            fact_id: Fact to verify.
            dimensions: Verification dimensions (default: accuracy, relevance, specificity).
            context: Optional additional context for the verifier.

        Returns:
            Dict with fact_id, verdict, scores, and reason.

        Raises:
            FactNotFoundError: If fact doesn't exist.
        """
        result = await self._session.execute(
            select(Fact).where(Fact.id == fact_id)
        )
        fact = result.scalar_one_or_none()
        if fact is None:
            raise FactNotFoundError(f"Fact {fact_id} not found")

        dims = dimensions or FACT_VERIFICATION_DIMENSIONS

        verification = await _call_fact_verifier(
            fact_text=fact.fact_text,
            category=fact.category,
            confidence=fact.confidence,
            dimensions=dims,
            context=context,
            llm_client=self._llm,
        )

        verdict = verification["verdict"]

        # Persist scores
        score_results = []
        for dim in dims:
            value, explanation = verification["scores"].get(
                dim, (0.5, "Dimension not scored")
            )
            score = Score(
                target_type="fact",
                target_id=fact_id,
                scorer="verification_engine",
                dimension=dim,
                value=value,
                explanation=explanation,
                branch_name=fact.branch_name,
            )
            self._session.add(score)
            score_results.append({
                "id": score.id,
                "dimension": dim,
                "value": value,
                "explanation": explanation,
            })

        # Update fact metadata with verification status
        metadata = dict(fact.metadata_json or {})
        metadata["verification_status"] = verdict
        metadata["verification_reason"] = verification["reason"]
        metadata["verified_at"] = datetime.utcnow().isoformat()

        await self._session.execute(
            update(Fact)
            .where(Fact.id == fact_id)
            .values(metadata_json=metadata)
        )

        await self._session.commit()

        return {
            "fact_id": fact_id,
            "verdict": verdict,
            "reason": verification["reason"],
            "scores": score_results,
        }

    async def batch_verify(
        self,
        branch_name: str,
        dimensions: list[str] | None = None,
        limit: int = 50,
        only_unverified: bool = True,
    ) -> dict:
        """Verify all unverified facts on a branch.

        Args:
            branch_name: Branch to verify facts on.
            dimensions: Verification dimensions.
            limit: Max facts to verify in one batch.
            only_unverified: If True, skip already-verified facts.

        Returns:
            Dict with verified, invalidated, unverified counts and details.
        """
        stmt = (
            select(Fact)
            .where(
                Fact.branch_name == branch_name,
                Fact.status == "active",
            )
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        facts = list(result.scalars().all())

        if only_unverified:
            facts = [
                f for f in facts
                if not (f.metadata_json or {}).get("verification_status")
            ]

        verified_count = 0
        invalidated_count = 0
        unverified_count = 0
        details = []

        for fact in facts:
            try:
                result = await self.verify_fact(
                    fact_id=fact.id,
                    dimensions=dimensions,
                )
                verdict = result["verdict"]
                if verdict == "verified":
                    verified_count += 1
                elif verdict == "invalidated":
                    invalidated_count += 1
                else:
                    unverified_count += 1
                details.append(result)
            except Exception as e:
                logger.error("Failed to verify fact %s: %s", fact.id, e)
                unverified_count += 1
                details.append({
                    "fact_id": fact.id,
                    "verdict": "error",
                    "reason": str(e),
                    "scores": [],
                })

        return {
            "branch_name": branch_name,
            "total_processed": len(facts),
            "verified": verified_count,
            "invalidated": invalidated_count,
            "unverified": unverified_count,
            "details": details,
        }

    async def get_verification_status(self, fact_id: str) -> dict:
        """Get the current verification status of a fact.

        Returns:
            Dict with fact_id, status, scores, and timestamp.
        """
        result = await self._session.execute(
            select(Fact).where(Fact.id == fact_id)
        )
        fact = result.scalar_one_or_none()
        if fact is None:
            raise FactNotFoundError(f"Fact {fact_id} not found")

        metadata = fact.metadata_json or {}
        status = metadata.get("verification_status", "unverified")

        # Get latest verification scores
        scores_result = await self._session.execute(
            select(Score)
            .where(
                Score.target_type == "fact",
                Score.target_id == fact_id,
                Score.scorer == "verification_engine",
            )
            .order_by(Score.created_at.desc())
        )
        scores = [
            {
                "dimension": s.dimension,
                "value": s.value,
                "explanation": s.explanation,
            }
            for s in scores_result.scalars().all()
        ]

        return {
            "fact_id": fact_id,
            "fact_text": fact.fact_text,
            "category": fact.category,
            "confidence": fact.confidence,
            "verification_status": status,
            "verification_reason": metadata.get("verification_reason"),
            "verified_at": metadata.get("verified_at"),
            "scores": scores,
        }

    async def get_verified_facts(
        self,
        branch_name: str,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get all verified facts on a branch.

        Args:
            branch_name: Branch to query.
            category: Optional category filter.
            limit: Max results.

        Returns:
            List of verified fact dicts.
        """
        stmt = (
            select(Fact)
            .where(
                Fact.branch_name == branch_name,
                Fact.status == "active",
            )
            .limit(limit)
        )
        if category:
            stmt = stmt.where(Fact.category == category)

        result = await self._session.execute(stmt)
        facts = result.scalars().all()

        return [
            {
                "id": f.id,
                "fact_text": f.fact_text,
                "category": f.category,
                "confidence": f.confidence,
                "verification_status": (f.metadata_json or {}).get(
                    "verification_status", "unverified"
                ),
            }
            for f in facts
            if (f.metadata_json or {}).get("verification_status") == "verified"
        ]

    async def check_merge_gate(
        self,
        source_branch: str,
        require_verified: bool = True,
    ) -> dict:
        """Check if a branch passes the merge gate.

        The merge gate ensures that only verified facts are merged to
        the parent branch. Returns a report on verification status.

        Args:
            source_branch: Branch to check.
            require_verified: If True, all facts must be verified.

        Returns:
            Dict with can_merge, total_facts, verified, unverified, invalidated.
        """
        result = await self._session.execute(
            select(Fact).where(
                Fact.branch_name == source_branch,
                Fact.status == "active",
            )
        )
        facts = list(result.scalars().all())

        verified = 0
        unverified = 0
        invalidated = 0
        unverified_facts = []

        for fact in facts:
            status = (fact.metadata_json or {}).get("verification_status", "unverified")
            if status == "verified":
                verified += 1
            elif status == "invalidated":
                invalidated += 1
            else:
                unverified += 1
                unverified_facts.append({
                    "id": fact.id,
                    "fact_text": fact.fact_text[:100],
                    "category": fact.category,
                })

        can_merge = True
        if require_verified and unverified > 0:
            can_merge = False
        if invalidated > 0:
            can_merge = False

        return {
            "source_branch": source_branch,
            "can_merge": can_merge,
            "total_facts": len(facts),
            "verified": verified,
            "unverified": unverified,
            "invalidated": invalidated,
            "unverified_facts": unverified_facts[:10],
        }

    async def get_branch_verification_summary(
        self,
        branch_name: str,
    ) -> dict:
        """Get a summary of verification status for all facts on a branch.

        Returns:
            Dict with counts by verification status and category.
        """
        result = await self._session.execute(
            select(Fact).where(
                Fact.branch_name == branch_name,
                Fact.status == "active",
            )
        )
        facts = list(result.scalars().all())

        by_status: dict[str, int] = {"verified": 0, "unverified": 0, "invalidated": 0}
        by_category: dict[str, dict[str, int]] = {}

        for fact in facts:
            status = (fact.metadata_json or {}).get("verification_status", "unverified")
            by_status[status] = by_status.get(status, 0) + 1

            cat = fact.category or "uncategorized"
            if cat not in by_category:
                by_category[cat] = {"verified": 0, "unverified": 0, "invalidated": 0}
            by_category[cat][status] = by_category[cat].get(status, 0) + 1

        return {
            "branch_name": branch_name,
            "total_facts": len(facts),
            "by_status": by_status,
            "by_category": by_category,
            "verification_rate": (
                round(by_status["verified"] / len(facts), 3)
                if facts
                else 0.0
            ),
        }
