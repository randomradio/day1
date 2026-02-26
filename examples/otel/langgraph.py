"""Example: send a LangGraph-like trace payload to the Day1 OTEL collector."""

from __future__ import annotations

import uuid

import httpx

from day1.otel.instrumentation.langgraph import build_ingest_payload


def main() -> None:
    payload = build_ingest_payload(
        trace_id=str(uuid.uuid4()),
        session_id="demo-langgraph",
        steps=[
            {"type": "user", "role": "user", "content": "Search for flaky test cause"},
            {"type": "tool_use", "node": "search", "summary": "Queried CI logs"},
            {
                "type": "assistant",
                "role": "assistant",
                "content": "Likely race in archive job",
            },
        ],
    )

    resp = httpx.post("http://127.0.0.1:4318/ingest", json=payload, timeout=5.0)
    resp.raise_for_status()
    print(resp.json())


if __name__ == "__main__":
    main()
