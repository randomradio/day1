"""Minimal trace collector placeholder for Day1 OTEL ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TraceEnvelope:
    """Normalized trace payload consumed by the Day1 collector."""

    source: str
    trace_id: str
    span_id: str | None = None
    session_id: str | None = None
    branch_name: str = "main"
    events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    received_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class TraceCollector:
    """In-memory collector with normalization hooks.

    This is a Day1 placeholder for future OTEL ingestion.
    It keeps recent envelopes in memory and exposes a conversion hook that
    later can persist conversations/messages/facts into the DB.
    """

    def __init__(self, max_items: int = 1000) -> None:
        self._max_items = max_items
        self._items: list[TraceEnvelope] = []

    def ingest(self, envelope: TraceEnvelope) -> dict[str, Any]:
        self._items.append(envelope)
        if len(self._items) > self._max_items:
            self._items = self._items[-self._max_items :]

        normalized = self.normalize(envelope)
        return {
            "status": "accepted",
            "source": envelope.source,
            "trace_id": envelope.trace_id,
            "events": len(envelope.events),
            "normalized": normalized,
        }

    def normalize(self, envelope: TraceEnvelope) -> dict[str, Any]:
        """Convert trace events to a DB-friendly placeholder structure."""
        messages = []
        observations = []
        for idx, event in enumerate(envelope.events, start=1):
            kind = str(event.get("kind", "event"))
            if kind in {"message", "assistant", "user"}:
                messages.append(
                    {
                        "sequence_num": idx,
                        "role": str(event.get("role", "assistant")),
                        "content": str(event.get("content", "")),
                    }
                )
            else:
                observations.append(
                    {
                        "observation_type": kind,
                        "summary": str(
                            event.get("summary") or event.get("content") or kind
                        ),
                    }
                )

        return {
            "session_id": envelope.session_id,
            "branch_name": envelope.branch_name,
            "messages": messages,
            "observations": observations,
            "metadata": envelope.metadata,
        }

    def recent(self, limit: int = 20) -> list[TraceEnvelope]:
        return list(self._items[-max(0, limit) :])
