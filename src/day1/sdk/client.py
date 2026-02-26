"""HTTPX-based Day1 REST SDK placeholder."""

from __future__ import annotations

from typing import Any

import httpx

from day1.sdk.types import GraphResponse, RelatedFactResponse, SearchResponse


class Day1Client:
    """Minimal sync REST client for Day1 API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Day1Client:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def write_fact(
        self,
        fact_text: str,
        *,
        branch: str = "main",
        category: str | None = None,
        confidence: float = 1.0,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "fact_text": fact_text,
            "branch": branch,
            "category": category,
            "confidence": confidence,
            "session_id": session_id,
            "metadata": metadata,
        }
        return self._request("POST", "/api/v1/facts", json=payload)

    def search(
        self,
        query: str,
        *,
        branch: str = "main",
        search_type: str = "keyword",
        limit: int = 10,
        category: str | None = None,
    ) -> SearchResponse:
        return self._request(
            "GET",
            "/api/v1/facts/search",
            params={
                "query": query,
                "branch": branch,
                "search_type": search_type,
                "limit": limit,
                "category": category,
            },
        )

    def get_fact_related(
        self,
        fact_id: str,
        *,
        branch: str | None = None,
        limit: int = 25,
    ) -> RelatedFactResponse:
        params = {"limit": limit}
        if branch:
            params["branch"] = branch
        return self._request(
            "GET",
            f"/api/v1/facts/{fact_id}/related",
            params=params,
        )

    def graph(
        self,
        *,
        entity: str | None = None,
        branch: str = "main",
        depth: int = 1,
        limit: int = 200,
    ) -> GraphResponse:
        params: dict[str, Any] = {
            "branch": branch,
            "depth": depth,
            "limit": limit,
        }
        if entity:
            params["entity"] = entity
        return self._request("GET", "/api/v1/relations/graph", params=params)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._client.request(method, path, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = None
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise httpx.HTTPStatusError(
                f"{exc}. response={detail}",
                request=exc.request,
                response=exc.response,
            ) from exc
        return resp.json()
