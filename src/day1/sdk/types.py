"""Typed response/request shapes for the Day1 REST SDK."""

from __future__ import annotations

from typing import Any, TypedDict


class FactRecord(TypedDict, total=False):
    id: str
    fact_text: str
    category: str | None
    confidence: float
    status: str
    branch_name: str
    created_at: str | None


class SearchResponse(TypedDict):
    results: list[FactRecord]
    count: int


class WriteFactRequest(TypedDict, total=False):
    fact_text: str
    category: str | None
    confidence: float
    source_type: str | None
    session_id: str | None
    branch: str
    metadata: dict[str, Any] | None


class RelatedFactResponse(TypedDict, total=False):
    fact: FactRecord
    entities: list[str]
    relations: list[dict[str, Any]]
    related_facts: list[FactRecord]
    count: int


class GraphResponse(TypedDict, total=False):
    mode: str
    entity: str | None
    relations: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    count: int

