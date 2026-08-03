from __future__ import annotations

from typing import Any, Dict, Tuple

from .api import ApiActor
from .base import ActorResult


class AdminActor(ApiActor):
    async def execute(self, action: str, params: Dict[str, Any], step_id: str) -> ActorResult:
        if action == "login":
            body = params.get("json") or {
                "username": params.get("username") or self.config.get("username"),
                "password": params.get("password") or self.config.get("password"),
            }
            result = await self.request("POST", "/api/v1/admin/auth/login", step_id=step_id, json_body=body)
            if result.status < 400 and isinstance(result.body, dict):
                self.token = result.body.get("access_token")
            return result

        method, path, body, query = self._build_request(action, params)
        return await self.request(
            method,
            path,
            step_id=step_id,
            json_body=body,
            query=query,
            tenant=True,
            write=method in {"POST", "PUT", "PATCH", "DELETE"},
            extra_headers=params.get("headers"),
            idempotency_key=params.get("idempotency_key"),
        )

    def _build_request(self, action: str, params: Dict[str, Any]) -> Tuple[str, str, Any, Any]:
        if action == "query" or params.get("path"):
            return (
                str(params.get("method", "GET" if action == "query" else "POST")).upper(),
                str(params["path"]),
                params.get("json"),
                params.get("query"),
            )
        if action == "create_site":
            return "POST", "/api/v1/sites", params, None
        if action == "register_charger":
            body = dict(params)
            site_id = body.pop("site_id", None)
            path = f"/api/v1/sites/{site_id}/charge-points" if site_id else "/api/v1/chargers"
            return "POST", path, body, None
        if action == "generate_qr":
            return (
                "POST",
                f"/api/v1/chargers/{params['charge_point_id']}/qr/{params.get('connector_id', 1)}/generate",
                None,
                None,
            )
        if action == "adjust_wallet":
            body = dict(params)
            user_id = body.pop("user_id")
            return "POST", f"/api/v1/admin/app-users/{user_id}/adjust-balance", body, None
        if action in {"remote_start", "remote_stop"}:
            suffix = "remote-start-transaction" if action == "remote_start" else "remote-stop-session"
            body = dict(params)
            if action == "remote_stop":
                # remote-stop-session requires Idempotency-Key as a header only.
                body.pop("idempotency_key", None)
            return "POST", f"/api/v1/ocpp/{suffix}", body, None
        if action in {"ack_alert", "resolve_alert"}:
            alert_id = params["alert_id"]
            suffix = "acknowledge" if action == "ack_alert" else "resolve"
            return "PUT", f"/api/v1/admin/alerts/{alert_id}/{suffix}", None, None
        raise ValueError(f"Unsupported admin action: {action}")
