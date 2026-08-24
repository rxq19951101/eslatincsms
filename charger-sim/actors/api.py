from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .base import ActorResult, BaseActor


class ApiActor(BaseActor):
    token: Optional[str] = None

    def __init__(self, name: str, config: Dict[str, Any], run_id: str):
        super().__init__(name, config, run_id)
        self.base_url = str(config.get("base_url", "http://localhost:9000")).rstrip("/")
        self.timeout = float(config.get("timeout", 15))
        self.client = httpx.AsyncClient(timeout=self.timeout)

    def auth_headers(
        self,
        step_id: str,
        *,
        tenant: bool = False,
        write: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if tenant and self.config.get("tenant_id"):
            headers["X-Tenant-Id"] = str(self.config["tenant_id"])
        if write:
            headers["Idempotency-Key"] = idempotency_key or f"{self.run_id}:{step_id}"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        step_id: str,
        json_body: Any = None,
        query: Optional[Dict[str, Any]] = None,
        tenant: bool = False,
        write: bool = False,
        extra_headers: Optional[Dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> ActorResult:
        headers = self.auth_headers(
            step_id,
            tenant=tenant,
            write=write,
            idempotency_key=idempotency_key,
        )
        if extra_headers:
            headers.update(extra_headers)
        url = path if path.startswith("http://") or path.startswith("https://") else f"{self.base_url}{path}"
        response = await self.client.request(method, url, json=json_body, params=query, headers=headers)
        try:
            body = response.json()
        except ValueError:
            body = {"text": response.text}
        return ActorResult(
            status=response.status_code,
            body=body,
            request={"method": method, "url": url, "json": json_body, "query": query, "headers": headers},
            response={"status_code": response.status_code, "body": body, "headers": dict(response.headers)},
            trace_id=response.headers.get("x-request-id") or response.headers.get("x-trace-id") or "",
        )

    async def close(self) -> None:
        await self.client.aclose()
