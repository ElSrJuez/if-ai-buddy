"""Async REST helper for the dfrotz wrapper."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import httpx

from module import my_logging
from module.my_logging import log_rest_event


@dataclass
class SessionHandle:
    pid: int
    name: str
    zfile: str
    label: str


class RestError(RuntimeError):
    """Raised when the dfrotz REST bridge responds with an error."""

    def __init__(self, status: int, message: str, *, endpoint: str) -> None:
        super().__init__(f"{endpoint} -> {status}: {message}")
        self.status = status
        self.endpoint = endpoint
        self.message = message


class RestResult:
    """Envelope returned by REST helper containing metadata."""

    def __init__(self, status_code: int, response: Any, timestamp: str) -> None:
        self.status_code = status_code
        self.response = response
        self.timestamp = timestamp


class DfrotzClient:
    """Thin, async wrapper around the dfrotz REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 15.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers or {})

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> None:
        await self._request("GET", "/")

    async def start_session(self, game: str, label: str) -> tuple[SessionHandle, str]:
        payload = {"game": game, "label": label}
        envelope = await self._request("POST", "/games", json=payload)
        data = envelope.response
        handle = SessionHandle(
            pid=data["pid"],
            name=data.get("name", game),
            zfile=data.get("zFile", ""),
            label=label,
        )
        return handle, data.get("data", "")

    async def submit_action(self, pid: int, action: str) -> dict[str, Any]:
        body = {"action": action}
        return await self._request("POST", f"/games/{pid}/action", json=body)

    async def stop_session(self, pid: int) -> None:
        await self._request("DELETE", f"/games/{pid}")

    async def list_titles(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/titles")
        return response.response

    async def list_games(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/games")
        return response.response

    async def _request(
        self,
        method: Literal["GET", "POST", "DELETE"],
        path: str,
        *,
        json: Any | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        # Log raw request payload (always logs minimal, debug logs full)
        log_rest_event({
            "stage": "request",
            "method": method,
            "url": url,
            "payload": json,
        })
        my_logging.system_debug(
            f"REST request {method} {url} payload={json if json is not None else '<none>'}"
        )
        try:
            response = await self._client.request(method, url, json=json)
        except httpx.HTTPError as exc:  # network/timeout
            my_logging.system_debug(f"REST error {method} {url}: {exc}")
            raise RestError(-1, str(exc), endpoint=url) from exc

        if response.status_code >= 400:
            my_logging.system_debug(
                f"REST response {method} {url} -> {response.status_code}: {response.text[:500]}"
            )
            raise RestError(response.status_code, response.text, endpoint=url)

        preview = response.text[:500]
        my_logging.system_debug(
            f"REST response {method} {url} -> {response.status_code}: {preview}"
        )

        # Deterministic JSON only for game-engine endpoints
        parsed = response.json()
        timestamp = datetime.utcnow().isoformat() + "Z"
        # Log raw response JSON (always logs minimal, debug logs full)
        log_rest_event({
            "stage": "response",
            "method": method,
            "url": url,
            "status_code": response.status_code,
            "response": parsed,
        })
        return RestResult(status_code=response.status_code, response=parsed, timestamp=timestamp)


__all__ = ["DfrotzClient", "RestError", "SessionHandle", "RestResult"]
