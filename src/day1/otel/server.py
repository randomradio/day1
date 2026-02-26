"""FastAPI server wrapper for OTEL collector placeholder."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from day1.otel.collector import TraceCollector, TraceEnvelope


class TraceIngestRequest(BaseModel):
    source: str = Field(..., description="langgraph | autogen | custom")
    trace_id: str
    span_id: str | None = None
    session_id: str | None = None
    branch_name: str = "main"
    events: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_otel_app(collector: TraceCollector | None = None) -> FastAPI:
    collector = collector or TraceCollector()
    app = FastAPI(title="Day1 OTEL Collector", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ingest")
    async def ingest(body: TraceIngestRequest) -> dict[str, Any]:
        envelope = TraceEnvelope(
            source=body.source,
            trace_id=body.trace_id,
            span_id=body.span_id,
            session_id=body.session_id,
            branch_name=body.branch_name,
            events=body.events,
            metadata=body.metadata,
        )
        return collector.ingest(envelope)

    @app.get("/recent")
    async def recent(limit: int = 20) -> dict[str, Any]:
        items = collector.recent(limit=limit)
        return {
            "items": [
                {
                    "source": item.source,
                    "trace_id": item.trace_id,
                    "span_id": item.span_id,
                    "session_id": item.session_id,
                    "branch_name": item.branch_name,
                    "received_at": item.received_at,
                    "events": item.events,
                }
                for item in items
            ],
            "count": len(items),
        }

    return app


app = create_otel_app()

