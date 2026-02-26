"""Semantic diff for agent conversations.

Unlike text diff which compares character sequences, semantic diff
decomposes conversations into three layers and compares each:

Layer 1 — Action Trace:  WHAT the agent did (tool calls, order, args)
Layer 2 — Reasoning Trace: WHY it chose that path (thinking + content)
Layer 3 — Outcome Summary: DID IT WORK (errors, efficiency, final state)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.embedding import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
    vecf32_to_embedding,
)
from day1.core.exceptions import ConversationNotFoundError
from day1.db.models import Conversation, Message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ActionStep:
    """A single tool call extracted from a conversation."""

    sequence_num: int
    tool_name: str
    arguments: dict | None = None
    result_snippet: str | None = None
    has_error: bool = False


@dataclass
class ActionDiffEntry:
    """One difference in the action traces."""

    op: str  # "same", "added_a", "added_b", "different_args", "reordered"
    tool_name: str
    detail: str = ""
    a_step: dict | None = None
    b_step: dict | None = None


@dataclass
class ReasoningSegment:
    """A reasoning chunk from assistant messages."""

    sequence_num: int
    content_snippet: str
    thinking_snippet: str | None = None
    embedding: list[float] | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SemanticDiffEngine:
    """Compare two agent conversations semantically across three layers."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder or get_embedding_provider()

    async def semantic_diff(
        self,
        conversation_a_id: str,
        conversation_b_id: str,
    ) -> dict:
        """Full semantic diff across all three layers.

        Args:
            conversation_a_id: First conversation (typically original).
            conversation_b_id: Second conversation (typically replay).

        Returns:
            Dict with action_diff, reasoning_diff, outcome_diff, and summary.
        """
        msgs_a = await self._load_messages(conversation_a_id)
        msgs_b = await self._load_messages(conversation_b_id)

        if not msgs_a:
            raise ConversationNotFoundError(
                f"No messages in conversation {conversation_a_id}"
            )
        if not msgs_b:
            raise ConversationNotFoundError(
                f"No messages in conversation {conversation_b_id}"
            )

        action_diff = self._diff_actions(msgs_a, msgs_b)
        reasoning_diff = await self._diff_reasoning(msgs_a, msgs_b)
        outcome_diff = self._diff_outcomes(msgs_a, msgs_b)

        # Find the divergence point (first message where they differ)
        divergence = self._find_divergence_point(msgs_a, msgs_b)

        return {
            "conversation_a": conversation_a_id,
            "conversation_b": conversation_b_id,
            "divergence_point": divergence,
            "action_diff": action_diff,
            "reasoning_diff": reasoning_diff,
            "outcome_diff": outcome_diff,
            "summary": self._build_summary(
                action_diff, reasoning_diff, outcome_diff, divergence
            ),
        }

    async def _load_messages(self, conversation_id: str) -> list[Message]:
        """Load messages for a conversation in sequence order."""
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_num.asc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Layer 1: Action Trace
    # ------------------------------------------------------------------

    def _diff_actions(
        self,
        msgs_a: list[Message],
        msgs_b: list[Message],
    ) -> dict:
        """Compare tool call sequences between two conversations."""
        actions_a = self._extract_actions(msgs_a)
        actions_b = self._extract_actions(msgs_b)

        seq_a = [a.tool_name for a in actions_a]
        seq_b = [a.tool_name for a in actions_b]

        # Tool sequence comparison
        entries: list[dict] = []
        tools_only_a: list[str] = []
        tools_only_b: list[str] = []
        common_tools: list[str] = []

        set_a = set(seq_a)
        set_b = set(seq_b)
        tools_only_a = sorted(set_a - set_b)
        tools_only_b = sorted(set_b - set_a)
        common_tools = sorted(set_a & set_b)

        # Walk both sequences to find ordering/argument differences
        # Use a simple LCS-like approach on tool names
        i, j = 0, 0
        while i < len(actions_a) and j < len(actions_b):
            a = actions_a[i]
            b = actions_b[j]
            if a.tool_name == b.tool_name:
                # Same tool — check if arguments differ
                if a.arguments != b.arguments:
                    entries.append({
                        "op": "different_args",
                        "tool": a.tool_name,
                        "a_sequence": a.sequence_num,
                        "b_sequence": b.sequence_num,
                        "a_args_snippet": _truncate_dict(a.arguments, 200),
                        "b_args_snippet": _truncate_dict(b.arguments, 200),
                    })
                else:
                    entries.append({
                        "op": "same",
                        "tool": a.tool_name,
                        "a_sequence": a.sequence_num,
                        "b_sequence": b.sequence_num,
                    })
                i += 1
                j += 1
            elif a.tool_name in set_b:
                # b has an extra tool before the match
                entries.append({
                    "op": "added_b",
                    "tool": b.tool_name,
                    "b_sequence": b.sequence_num,
                })
                j += 1
            elif b.tool_name in set_a:
                # a has an extra tool before the match
                entries.append({
                    "op": "added_a",
                    "tool": a.tool_name,
                    "a_sequence": a.sequence_num,
                })
                i += 1
            else:
                # Both have different tools at this position
                entries.append({
                    "op": "replaced",
                    "a_tool": a.tool_name,
                    "b_tool": b.tool_name,
                    "a_sequence": a.sequence_num,
                    "b_sequence": b.sequence_num,
                })
                i += 1
                j += 1

        # Remaining actions
        while i < len(actions_a):
            entries.append({
                "op": "added_a",
                "tool": actions_a[i].tool_name,
                "a_sequence": actions_a[i].sequence_num,
            })
            i += 1
        while j < len(actions_b):
            entries.append({
                "op": "added_b",
                "tool": actions_b[j].tool_name,
                "b_sequence": actions_b[j].sequence_num,
            })
            j += 1

        # Error comparison
        errors_a = [a for a in actions_a if a.has_error]
        errors_b = [a for a in actions_b if a.has_error]

        # Sequence order similarity (Kendall-tau-like)
        order_sim = _sequence_similarity(seq_a, seq_b)

        return {
            "a_tool_count": len(actions_a),
            "b_tool_count": len(actions_b),
            "tools_only_in_a": tools_only_a,
            "tools_only_in_b": tools_only_b,
            "common_tools": common_tools,
            "sequence_similarity": order_sim,
            "a_errors": len(errors_a),
            "b_errors": len(errors_b),
            "entries": entries,
        }

    def _extract_actions(self, messages: list[Message]) -> list[ActionStep]:
        """Extract tool call actions from messages."""
        actions: list[ActionStep] = []
        # Build a map of tool_call seq_num -> next tool_result
        tool_results: dict[int, Message] = {}
        for m in messages:
            if m.role == "tool_result":
                # Associate with preceding tool_call
                tool_results[m.sequence_num] = m

        for m in messages:
            if m.role == "tool_call" and m.tool_calls_json:
                calls = m.tool_calls_json
                if isinstance(calls, list):
                    for call in calls:
                        name = call.get("name", "unknown")
                        args = call.get("input") or call.get("arguments")
                        # Look for result in next message
                        result_msg = tool_results.get(m.sequence_num + 1)
                        result_snippet = None
                        has_error = False
                        if result_msg and result_msg.content:
                            result_snippet = result_msg.content[:200]
                            content_lower = result_msg.content.lower()
                            has_error = any(
                                kw in content_lower
                                for kw in ("error", "exception", "failed", "traceback")
                            )
                        actions.append(ActionStep(
                            sequence_num=m.sequence_num,
                            tool_name=name,
                            arguments=args,
                            result_snippet=result_snippet,
                            has_error=has_error,
                        ))
                elif isinstance(calls, dict):
                    name = calls.get("name", "unknown")
                    args = calls.get("input") or calls.get("arguments")
                    actions.append(ActionStep(
                        sequence_num=m.sequence_num,
                        tool_name=name,
                        arguments=args,
                    ))
        return actions

    # ------------------------------------------------------------------
    # Layer 2: Reasoning Trace
    # ------------------------------------------------------------------

    async def _diff_reasoning(
        self,
        msgs_a: list[Message],
        msgs_b: list[Message],
    ) -> dict:
        """Compare reasoning traces semantically via embedding similarity."""
        segments_a = self._extract_reasoning(msgs_a)
        segments_b = self._extract_reasoning(msgs_b)

        if not segments_a or not segments_b:
            return {
                "a_reasoning_steps": len(segments_a),
                "b_reasoning_steps": len(segments_b),
                "overall_similarity": 0.0,
                "pairs": [],
            }

        # Get embeddings for reasoning segments
        texts_a = [s.content_snippet for s in segments_a]
        texts_b = [s.content_snippet for s in segments_b]

        try:
            embeds_a = await self._embedder.embed_batch(texts_a)
            embeds_b = await self._embedder.embed_batch(texts_b)
        except Exception:
            # Fall back to stored embeddings if available
            embeds_a = [
                s.embedding for s in segments_a
            ]
            embeds_b = [
                s.embedding for s in segments_b
            ]

        # Pair up reasoning segments (align by position, not content)
        pairs: list[dict] = []
        max_pairs = min(len(segments_a), len(segments_b))
        total_sim = 0.0

        for idx in range(max_pairs):
            ea = embeds_a[idx] if idx < len(embeds_a) else None
            eb = embeds_b[idx] if idx < len(embeds_b) else None

            sim = 0.0
            if ea and eb:
                sim = cosine_similarity(ea, eb)

            pairs.append({
                "position": idx,
                "a_sequence": segments_a[idx].sequence_num,
                "b_sequence": segments_b[idx].sequence_num,
                "similarity": round(sim, 3),
                "a_snippet": segments_a[idx].content_snippet[:200],
                "b_snippet": segments_b[idx].content_snippet[:200],
                "diverged": sim < 0.7,
            })
            total_sim += sim

        overall = round(total_sim / max_pairs, 3) if max_pairs else 0.0

        return {
            "a_reasoning_steps": len(segments_a),
            "b_reasoning_steps": len(segments_b),
            "overall_similarity": overall,
            "pairs": pairs,
        }

    def _extract_reasoning(
        self,
        messages: list[Message],
    ) -> list[ReasoningSegment]:
        """Extract reasoning from assistant messages."""
        segments: list[ReasoningSegment] = []
        for m in messages:
            if m.role != "assistant":
                continue
            content = m.content or ""
            if not content.strip():
                continue

            embedding = None
            if m.embedding:
                embedding = vecf32_to_embedding(m.embedding)

            segments.append(ReasoningSegment(
                sequence_num=m.sequence_num,
                content_snippet=content[:500],
                thinking_snippet=(
                    m.thinking[:300] if m.thinking else None
                ),
                embedding=embedding,
            ))
        return segments

    # ------------------------------------------------------------------
    # Layer 3: Outcome
    # ------------------------------------------------------------------

    def _diff_outcomes(
        self,
        msgs_a: list[Message],
        msgs_b: list[Message],
    ) -> dict:
        """Compare aggregate outcomes between two conversations."""
        stats_a = self._compute_outcome_stats(msgs_a)
        stats_b = self._compute_outcome_stats(msgs_b)

        return {
            "a": stats_a,
            "b": stats_b,
            "delta": {
                "messages": stats_b["message_count"] - stats_a["message_count"],
                "tokens": stats_b["total_tokens"] - stats_a["total_tokens"],
                "tool_calls": (
                    stats_b["tool_call_count"] - stats_a["tool_call_count"]
                ),
                "errors": stats_b["error_count"] - stats_a["error_count"],
            },
            "efficiency": _efficiency_label(stats_a, stats_b),
        }

    def _compute_outcome_stats(self, messages: list[Message]) -> dict:
        """Compute outcome statistics for a conversation."""
        total_tokens = sum(m.token_count for m in messages)
        tool_calls = [m for m in messages if m.role == "tool_call"]
        tool_results = [m for m in messages if m.role == "tool_result"]
        errors = [
            m for m in tool_results
            if m.content and any(
                kw in m.content.lower()
                for kw in ("error", "exception", "failed", "traceback")
            )
        ]
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        final_msg = assistant_msgs[-1] if assistant_msgs else None

        return {
            "message_count": len(messages),
            "total_tokens": total_tokens,
            "tool_call_count": len(tool_calls),
            "tool_result_count": len(tool_results),
            "error_count": len(errors),
            "assistant_messages": len(assistant_msgs),
            "final_message_snippet": (
                (final_msg.content or "")[:300] if final_msg else None
            ),
            "models_used": list({
                m.model for m in messages if m.model
            }),
        }

    # ------------------------------------------------------------------
    # Divergence detection
    # ------------------------------------------------------------------

    def _find_divergence_point(
        self,
        msgs_a: list[Message],
        msgs_b: list[Message],
    ) -> dict:
        """Find where two conversations first diverge."""
        min_len = min(len(msgs_a), len(msgs_b))
        diverge_idx = min_len  # default: they're identical up to shorter

        for i in range(min_len):
            a = msgs_a[i]
            b = msgs_b[i]
            if a.role != b.role or a.content != b.content:
                diverge_idx = i
                break

        shared = diverge_idx
        if diverge_idx < min_len:
            return {
                "shared_prefix_length": shared,
                "a_diverges_at_sequence": msgs_a[diverge_idx].sequence_num,
                "b_diverges_at_sequence": msgs_b[diverge_idx].sequence_num,
                "a_diverge_role": msgs_a[diverge_idx].role,
                "b_diverge_role": msgs_b[diverge_idx].role,
                "a_diverge_snippet": (
                    (msgs_a[diverge_idx].content or "")[:200]
                ),
                "b_diverge_snippet": (
                    (msgs_b[diverge_idx].content or "")[:200]
                ),
            }

        return {
            "shared_prefix_length": shared,
            "note": "Conversations share identical messages up to the shorter one",
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        action_diff: dict,
        reasoning_diff: dict,
        outcome_diff: dict,
        divergence: dict,
    ) -> dict:
        """Build a human-readable summary of the semantic diff."""
        # Action verdict
        same_count = sum(
            1 for e in action_diff["entries"] if e["op"] == "same"
        )
        total_entries = len(action_diff["entries"])
        action_match = (
            round(same_count / total_entries, 2) if total_entries else 1.0
        )

        # Determine overall verdict
        reasoning_sim = reasoning_diff["overall_similarity"]
        delta = outcome_diff["delta"]

        if action_match > 0.8 and reasoning_sim > 0.8:
            verdict = "equivalent"
            description = (
                "Both conversations took essentially the same approach"
                " and reached similar conclusions."
            )
        elif action_match > 0.5 and reasoning_sim > 0.5:
            verdict = "similar"
            description = (
                "The conversations follow a related strategy but diverge"
                " in some tool choices or reasoning steps."
            )
        elif action_match < 0.3:
            verdict = "divergent"
            description = (
                "The conversations took fundamentally different approaches"
                " to the task."
            )
        else:
            verdict = "mixed"
            description = (
                "Some overlap in approach but significant differences"
                " in execution."
            )

        # Efficiency note
        efficiency = outcome_diff["efficiency"]

        return {
            "verdict": verdict,
            "description": description,
            "action_match": action_match,
            "reasoning_similarity": reasoning_sim,
            "efficiency": efficiency,
            "shared_prefix": divergence["shared_prefix_length"],
            "a_total_tokens": outcome_diff["a"]["total_tokens"],
            "b_total_tokens": outcome_diff["b"]["total_tokens"],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate_dict(d: dict | None, max_chars: int) -> str | None:
    """Truncate a dict's string repr for display."""
    if d is None:
        return None
    s = str(d)
    if len(s) > max_chars:
        return s[:max_chars] + "..."
    return s


def _sequence_similarity(seq_a: list[str], seq_b: list[str]) -> float:
    """Compute ordering similarity between two tool name sequences.

    Uses the ratio of common bigrams to total bigrams — a lightweight
    proxy for how similar the ordering is.
    """
    if not seq_a and not seq_b:
        return 1.0
    if not seq_a or not seq_b:
        return 0.0

    bigrams_a = set(zip(seq_a, seq_a[1:])) if len(seq_a) > 1 else set()
    bigrams_b = set(zip(seq_b, seq_b[1:])) if len(seq_b) > 1 else set()

    if not bigrams_a and not bigrams_b:
        # Single-tool sequences — compare the single item
        return 1.0 if seq_a == seq_b else 0.0

    union = bigrams_a | bigrams_b
    if not union:
        return 0.0

    intersection = bigrams_a & bigrams_b
    return round(len(intersection) / len(union), 3)


def _efficiency_label(stats_a: dict, stats_b: dict) -> str:
    """Compare which conversation was more efficient."""
    token_a = stats_a["total_tokens"]
    token_b = stats_b["total_tokens"]
    errors_a = stats_a["error_count"]
    errors_b = stats_b["error_count"]

    if token_a == 0 and token_b == 0:
        return "equal"

    # Fewer errors is better, then fewer tokens
    if errors_a < errors_b:
        return "a_better"
    if errors_b < errors_a:
        return "b_better"

    if token_a == token_b:
        return "equal"

    # Within 10% is roughly equal
    ratio = token_b / token_a if token_a > 0 else float("inf")
    if 0.9 <= ratio <= 1.1:
        return "roughly_equal"
    return "a_better" if token_a < token_b else "b_better"
