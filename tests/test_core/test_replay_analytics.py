"""Tests for ReplayEngine, AnalyticsEngine, SemanticDiffEngine, ScoringEngine."""

from __future__ import annotations

import pytest
import pytest_asyncio

from branchedmind.core.analytics_engine import AnalyticsEngine
from branchedmind.core.conversation_engine import ConversationEngine
from branchedmind.core.embedding import MockEmbedding
from branchedmind.core.exceptions import ConversationNotFoundError, ReplayError
from branchedmind.core.message_engine import MessageEngine
from branchedmind.core.replay_engine import ReplayConfig, ReplayEngine
from branchedmind.core.scoring_engine import HeuristicScorer, ScoringEngine
from branchedmind.core.semantic_diff import SemanticDiffEngine


# --- Helpers ---


async def _create_conversation_with_messages(
    db_session,
    mock_embedder,
    session_id: str = "test-session",
    title: str = "Test Conv",
    messages: list[dict] | None = None,
) -> tuple[str, list[str]]:
    """Create a conversation with messages, return (conv_id, [msg_ids])."""
    conv_engine = ConversationEngine(db_session)
    msg_engine = MessageEngine(db_session, mock_embedder)

    conv = await conv_engine.create_conversation(
        session_id=session_id, title=title
    )

    if messages is None:
        messages = [
            {"role": "user", "content": "Hello, can you help me?"},
            {"role": "assistant", "content": "Of course! What do you need?"},
            {"role": "user", "content": "Search for the config file"},
            {
                "role": "tool_call",
                "content": None,
                "tool_calls": [{"name": "Grep", "input": {"query": "config"}}],
            },
            {"role": "tool_result", "content": "Found config.py at line 42"},
            {
                "role": "assistant",
                "content": "I found the config file at config.py:42.",
            },
        ]

    msg_ids = []
    for m in messages:
        msg = await msg_engine.write_message(
            conversation_id=conv.id,
            role=m["role"],
            content=m.get("content"),
            tool_calls=m.get("tool_calls"),
            session_id=session_id,
            embed=False,
        )
        msg_ids.append(msg.id)

    return conv.id, msg_ids


# =====================================================================
# ReplayEngine tests
# =====================================================================


class TestReplayEngine:
    @pytest.mark.asyncio
    async def test_start_replay_forks_conversation(
        self, db_session, mock_embedder
    ):
        conv_id, msg_ids = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ReplayEngine(db_session)
        result = await engine.start_replay(
            conversation_id=conv_id,
            from_message_id=msg_ids[2],  # Fork after "Search for the config file"
        )
        assert result.status == "ready"
        assert result.original_conversation_id == conv_id
        assert result.forked_conversation_id != conv_id
        assert result.messages_copied == 3  # First 3 messages

    @pytest.mark.asyncio
    async def test_replay_with_config(self, db_session, mock_embedder):
        conv_id, msg_ids = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ReplayEngine(db_session)
        config = ReplayConfig(
            model="claude-opus-4-20250514",
            system_prompt="Be very concise.",
            title="Replay with Opus",
        )
        result = await engine.start_replay(
            conversation_id=conv_id,
            from_message_id=msg_ids[1],
            config=config,
        )
        assert result.config["model"] == "claude-opus-4-20250514"
        assert result.config["system_prompt"] == "Be very concise."

    @pytest.mark.asyncio
    async def test_replay_with_extra_context(self, db_session, mock_embedder):
        conv_id, msg_ids = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ReplayEngine(db_session)
        config = ReplayConfig(extra_context="Focus on Python files only.")
        result = await engine.start_replay(
            conversation_id=conv_id,
            from_message_id=msg_ids[1],
            config=config,
        )
        # Extra context adds a system message, so copies + 1
        assert result.messages_copied == 2  # First 2 messages
        # Verify the context was added via get_replay_context
        ctx = await engine.get_replay_context(result.forked_conversation_id)
        system_msgs = [m for m in ctx["messages"] if m["role"] == "system"]
        assert len(system_msgs) >= 1
        assert "Python files" in system_msgs[-1]["content"]

    @pytest.mark.asyncio
    async def test_replay_context_returns_messages(
        self, db_session, mock_embedder
    ):
        conv_id, msg_ids = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ReplayEngine(db_session)
        result = await engine.start_replay(
            conversation_id=conv_id, from_message_id=msg_ids[2]
        )
        ctx = await engine.get_replay_context(result.forked_conversation_id)
        assert ctx["original_conversation_id"] == conv_id
        assert len(ctx["messages"]) == 3

    @pytest.mark.asyncio
    async def test_complete_replay(self, db_session, mock_embedder):
        conv_id, msg_ids = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ReplayEngine(db_session)
        result = await engine.start_replay(
            conversation_id=conv_id, from_message_id=msg_ids[1]
        )
        completed = await engine.complete_replay(
            result.forked_conversation_id
        )
        assert completed["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_replays(self, db_session, mock_embedder):
        conv_id, msg_ids = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ReplayEngine(db_session)
        await engine.start_replay(
            conversation_id=conv_id, from_message_id=msg_ids[1]
        )
        await engine.start_replay(
            conversation_id=conv_id, from_message_id=msg_ids[2]
        )
        replays = await engine.list_replays(conversation_id=conv_id)
        assert len(replays) == 2

    @pytest.mark.asyncio
    async def test_diff_replay(self, db_session, mock_embedder):
        conv_id, msg_ids = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ReplayEngine(db_session)
        result = await engine.start_replay(
            conversation_id=conv_id, from_message_id=msg_ids[2]
        )
        diff = await engine.diff_replay(result.forked_conversation_id)
        assert diff["conversation_a"] == conv_id
        assert diff["conversation_b"] == result.forked_conversation_id

    @pytest.mark.asyncio
    async def test_replay_nonexistent_conversation(self, db_session):
        engine = ReplayEngine(db_session)
        with pytest.raises(ConversationNotFoundError):
            await engine.start_replay(
                conversation_id="nonexistent",
                from_message_id="whatever",
            )


# =====================================================================
# AnalyticsEngine tests
# =====================================================================


class TestAnalyticsEngine:
    @pytest.mark.asyncio
    async def test_overview_empty(self, db_session):
        engine = AnalyticsEngine(db_session)
        result = await engine.overview()
        assert "counts" in result
        assert "tokens" in result
        assert "activity" in result
        assert "consolidation" in result

    @pytest.mark.asyncio
    async def test_overview_with_data(self, db_session, mock_embedder):
        await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = AnalyticsEngine(db_session)
        result = await engine.overview()
        assert result["counts"]["conversations"] >= 1
        assert result["counts"]["messages"] >= 6

    @pytest.mark.asyncio
    async def test_session_analytics(self, db_session, mock_embedder):
        await _create_conversation_with_messages(
            db_session, mock_embedder, session_id="analytics-session"
        )
        engine = AnalyticsEngine(db_session)
        result = await engine.session_analytics("analytics-session")
        assert result["session_id"] == "analytics-session"
        assert result["conversations"] >= 1
        assert result["total_messages"] >= 6

    @pytest.mark.asyncio
    async def test_session_analytics_not_found(self, db_session):
        engine = AnalyticsEngine(db_session)
        result = await engine.session_analytics("nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_conversation_analytics(self, db_session, mock_embedder):
        conv_id, _ = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = AnalyticsEngine(db_session)
        result = await engine.conversation_analytics(conv_id)
        assert result["message_count"] == 6
        assert "message_roles" in result
        assert result["message_roles"]["user"] == 2
        assert result["message_roles"]["assistant"] == 2

    @pytest.mark.asyncio
    async def test_trends(self, db_session, mock_embedder):
        await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = AnalyticsEngine(db_session)
        result = await engine.trends(days=7)
        assert "messages" in result
        assert "facts" in result
        assert "conversations" in result


# =====================================================================
# SemanticDiffEngine tests
# =====================================================================


class TestSemanticDiffEngine:
    @pytest.mark.asyncio
    async def test_semantic_diff_identical_conversations(
        self, db_session, mock_embedder
    ):
        """Two identical conversations should be 'equivalent'."""
        conv_a, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="Conv A"
        )
        conv_b, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="Conv B"
        )
        engine = SemanticDiffEngine(db_session, mock_embedder)
        result = await engine.semantic_diff(conv_a, conv_b)
        assert result["summary"]["verdict"] in ("equivalent", "similar")
        assert result["outcome_diff"]["delta"]["messages"] == 0

    @pytest.mark.asyncio
    async def test_semantic_diff_different_conversations(
        self, db_session, mock_embedder
    ):
        """Conversations with different tools should show in action diff."""
        msgs_a = [
            {"role": "user", "content": "Find the bug"},
            {
                "role": "tool_call",
                "content": None,
                "tool_calls": [{"name": "Grep", "input": {"query": "bug"}}],
            },
            {"role": "tool_result", "content": "Found bug at line 10"},
            {"role": "assistant", "content": "Fixed the bug."},
        ]
        msgs_b = [
            {"role": "user", "content": "Find the bug"},
            {
                "role": "tool_call",
                "content": None,
                "tool_calls": [{"name": "Read", "input": {"file": "main.py"}}],
            },
            {"role": "tool_result", "content": "File contents..."},
            {
                "role": "tool_call",
                "content": None,
                "tool_calls": [{"name": "Edit", "input": {"file": "main.py"}}],
            },
            {"role": "tool_result", "content": "Edit applied"},
            {"role": "assistant", "content": "I read and edited the file."},
        ]
        conv_a, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="A", messages=msgs_a
        )
        conv_b, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="B", messages=msgs_b
        )
        engine = SemanticDiffEngine(db_session, mock_embedder)
        result = await engine.semantic_diff(conv_a, conv_b)
        action = result["action_diff"]
        assert action["a_tool_count"] == 1
        assert action["b_tool_count"] == 2
        assert "Grep" in action["tools_only_in_a"]

    @pytest.mark.asyncio
    async def test_semantic_diff_outcome(self, db_session, mock_embedder):
        """Outcome diff should show delta in message counts."""
        msgs_short = [
            {"role": "user", "content": "Do it"},
            {"role": "assistant", "content": "Done."},
        ]
        msgs_long = [
            {"role": "user", "content": "Do it"},
            {"role": "assistant", "content": "Let me think..."},
            {"role": "user", "content": "Go on"},
            {"role": "assistant", "content": "Done."},
        ]
        conv_a, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="Short", messages=msgs_short
        )
        conv_b, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="Long", messages=msgs_long
        )
        engine = SemanticDiffEngine(db_session, mock_embedder)
        result = await engine.semantic_diff(conv_a, conv_b)
        assert result["outcome_diff"]["delta"]["messages"] == 2

    @pytest.mark.asyncio
    async def test_divergence_point(self, db_session, mock_embedder):
        """Should find where conversations diverge."""
        msgs_a = [
            {"role": "user", "content": "Start"},
            {"role": "assistant", "content": "Path A"},
        ]
        msgs_b = [
            {"role": "user", "content": "Start"},
            {"role": "assistant", "content": "Path B"},
        ]
        conv_a, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="A", messages=msgs_a
        )
        conv_b, _ = await _create_conversation_with_messages(
            db_session, mock_embedder, title="B", messages=msgs_b
        )
        engine = SemanticDiffEngine(db_session, mock_embedder)
        result = await engine.semantic_diff(conv_a, conv_b)
        assert result["divergence_point"]["shared_prefix_length"] == 1


# =====================================================================
# ScoringEngine tests
# =====================================================================


class TestScoringEngine:
    @pytest.mark.asyncio
    async def test_score_conversation_heuristic(
        self, db_session, mock_embedder
    ):
        conv_id, _ = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ScoringEngine(db_session)
        scores = await engine.score_conversation(conv_id)
        assert len(scores) == 4  # 4 heuristic dimensions
        for s in scores:
            assert 0.0 <= s["value"] <= 1.0
            assert s["dimension"] in (
                "token_efficiency", "error_rate",
                "tool_success", "conciseness",
            )

    @pytest.mark.asyncio
    async def test_score_specific_dimensions(
        self, db_session, mock_embedder
    ):
        conv_id, _ = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ScoringEngine(db_session)
        scores = await engine.score_conversation(
            conv_id, dimensions=["error_rate"]
        )
        assert len(scores) == 1
        assert scores[0]["dimension"] == "error_rate"

    @pytest.mark.asyncio
    async def test_create_manual_score(self, db_session):
        engine = ScoringEngine(db_session)
        score = await engine.create_score(
            target_type="conversation",
            target_id="some-id",
            scorer="human",
            dimension="helpfulness",
            value=0.9,
            explanation="Very helpful response.",
        )
        assert score["value"] == 0.9
        assert score["scorer"] == "human"

    @pytest.mark.asyncio
    async def test_list_scores(self, db_session, mock_embedder):
        conv_id, _ = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ScoringEngine(db_session)
        await engine.score_conversation(conv_id)
        scores = await engine.list_scores(target_id=conv_id)
        assert len(scores) == 4

    @pytest.mark.asyncio
    async def test_score_summary(self, db_session, mock_embedder):
        conv_id, _ = await _create_conversation_with_messages(
            db_session, mock_embedder
        )
        engine = ScoringEngine(db_session)
        await engine.score_conversation(conv_id)
        summary = await engine.get_score_summary("conversation", conv_id)
        assert "dimensions" in summary
        assert "error_rate" in summary["dimensions"]

    @pytest.mark.asyncio
    async def test_clamp_score_value(self, db_session):
        engine = ScoringEngine(db_session)
        score = await engine.create_score(
            target_type="message",
            target_id="test",
            scorer="test",
            dimension="test",
            value=1.5,  # Should clamp to 1.0
        )
        assert score["value"] == 1.0


# =====================================================================
# HeuristicScorer unit tests
# =====================================================================


class TestHeuristicScorer:
    @pytest.mark.asyncio
    async def test_error_rate_no_errors(self):
        scorer = HeuristicScorer()
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.role = "tool_result"
        msg.content = "Success: file found"
        value, explanation = await scorer.score([msg], "error_rate")
        assert value == 1.0

    @pytest.mark.asyncio
    async def test_error_rate_with_errors(self):
        scorer = HeuristicScorer()
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.role = "tool_result"
        msg.content = "Error: file not found"
        value, explanation = await scorer.score([msg], "error_rate")
        assert value == 0.0

    @pytest.mark.asyncio
    async def test_unknown_dimension(self):
        scorer = HeuristicScorer()
        value, explanation = await scorer.score([], "unknown_dim")
        assert value == 0.5
