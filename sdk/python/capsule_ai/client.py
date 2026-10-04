"""HTTP client for the Capsule API at http://127.0.0.1:9100."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Mapping, Optional

import httpx


class KapsuleError(Exception):
    """Raised when the Capsule API returns a non-success status."""

    def __init__(self, status: int, detail: Any) -> None:
        self.status = status
        self.detail = detail
        super().__init__(_error_message(status, detail))


class KapsuleClient:
    """Thin client for Capsule's `/health` and `/api/v1` routes.

    The full engine remains the `kapsule` package. This client only speaks HTTP.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9100",
        api_token: Optional[str] = None,
        timeout: float = 30.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "KapsuleClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/status")

    def create_capsule(
        self,
        topic: str,
        content: str,
        tags: Optional[list[str]] = None,
        freshness: Optional[str] = None,
        source: Optional[str] = None,
        confidence: str = "medium",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/capsules",
            {
                "topic": topic,
                "content": content,
                "tags": tags or [],
                "freshness": freshness,
                "source": source,
                "confidence": confidence,
            },
        )

    def list_capsules(
        self,
        archived: Optional[bool] = None,
        tag: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/capsules",
            query={"archived": archived, "tag": tag, "limit": limit, "offset": offset},
        )

    def get_capsule(self, capsule_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/capsules/{capsule_id}")

    def update_capsule(self, capsule_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"topic", "content", "tags", "freshness", "source", "confidence"}
        unknown = set(fields) - allowed
        if unknown:
            raise TypeError(f"Unknown capsule fields: {', '.join(sorted(unknown))}")
        return self._request("PATCH", f"/api/v1/capsules/{capsule_id}", fields)

    def delete_capsule(self, capsule_id: str) -> None:
        self._request("DELETE", f"/api/v1/capsules/{capsule_id}")

    def archive_capsule(self, capsule_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/capsules/{capsule_id}/archive")

    def search(
        self,
        query: str = "",
        tags: Optional[list[str]] = None,
        confidence: Optional[str] = None,
        archived: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        mode: str = "fts",
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"query": query, "mode": mode}
        if tags is not None:
            body["tags"] = tags
        if confidence is not None:
            body["confidence"] = confidence
        if archived is not None:
            body["archived"] = archived
        if limit is not None:
            body["limit"] = limit
        if offset is not None:
            body["offset"] = offset
        return self._request("POST", "/api/v1/search", body)

    def compose(
        self,
        query: Optional[str] = None,
        tags: Optional[list[str]] = None,
        confidence_min: Optional[str] = None,
        max_tokens: Optional[int] = None,
        mode: Optional[str] = None,
        graph_expansion: Optional[bool] = None,
        max_hops: Optional[int] = None,
        affinity_weight: Optional[float] = None,
        include_superseded: Optional[bool] = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/compose",
            {
                "query": query,
                "tags": tags,
                "confidence_min": confidence_min,
                "max_tokens": max_tokens,
                "mode": mode,
                "graph_expansion": graph_expansion,
                "max_hops": max_hops,
                "affinity_weight": affinity_weight,
                "include_superseded": include_superseded,
            },
        )

    def list_relationships(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/relationships")

    def create_relationship(
        self,
        from_id: str,
        to_id: str,
        relationship_type: str = "relates_to",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/relationships",
            {
                "from_capsule_id": from_id,
                "to_capsule_id": to_id,
                "relationship_type": relationship_type,
            },
        )

    def capsule_relationships(self, capsule_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/capsules/{capsule_id}/relationships")

    def list_tags(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/tags")

    def stale(self, days: int = 90) -> dict[str, Any]:
        return self._request("GET", "/api/v1/stale", query={"days": days})

    def sync(self) -> dict[str, Any]:
        return self._request("POST", "/api/v1/sync")

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        params = None
        if query:
            params = {key: value for key, value in query.items() if value is not None}
        payload = None
        if body is not None:
            payload = {key: value for key, value in body.items() if value is not None}
        response = self._client.request(method, path, json=payload, params=params)
        if response.status_code == 204:
            return None
        parsed: Any = None
        if response.content:
            try:
                parsed = response.json()
            except ValueError:
                parsed = response.text
        if response.is_error:
            raise KapsuleError(response.status_code, parsed)
        return parsed


def _error_message(status: int, detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict) and "detail" in detail:
        return str(detail["detail"])
    return f"Kapsule API error {status}"
