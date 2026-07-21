from __future__ import annotations

from typing import Any, Dict, Tuple
import uuid

from .api import ApiActor
from .base import ActorResult


class AppUserActor(ApiActor):
    async def execute(self, action: str, params: Dict[str, Any], step_id: str) -> ActorResult:
        if action in {"register", "login"}:
            path = "/api/v1/app/auth/register-email" if action == "register" else "/api/v1/app/auth/login-email"
            body = params.get("json") or {
                "email": params.get("email") or self.config.get("email"),
                "password": params.get("password") or self.config.get("password"),
            }
            if action == "register":
                for key in ("full_name", "phone"):
                    value = params.get(key) or self.config.get(key)
                    if value is not None:
                        body[key] = value
            result = await self.request("POST", path, step_id=step_id, json_body=body)
            if result.status < 400 and isinstance(result.body, dict):
                self.token = result.body.get("access_token")
            return result

        method, path, body, query = self._build_request(action, params)
        result = await self.request(
            method,
            path,
            step_id=step_id,
            json_body=body,
            query=query,
            write=method in {"POST", "PUT", "PATCH", "DELETE"},
            extra_headers=params.get("headers"),
            idempotency_key=params.get("idempotency_key"),
        )
        if result.status < 400:
            self._validate_resource_ids(action, result.body)
        return result

    @staticmethod
    def _require_uuid(value: Any, field: str) -> None:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a UUID string")
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be a UUID string") from exc

    @classmethod
    def _validate_resource_ids(cls, action: str, body: Any) -> None:
        if action == "get_active" and isinstance(body, dict):
            for field in ("id", "charge_point_id", "evse_id"):
                if body.get(field) is not None:
                    cls._require_uuid(body[field], field)
            transaction_id = body.get("transaction_id")
            if transaction_id is not None and (not isinstance(transaction_id, int) or transaction_id <= 0):
                raise ValueError("transaction_id must be a positive OCPP integer")
        if action == "get_meter_values":
            items = body.get("items", body) if isinstance(body, dict) else body
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("id") is not None:
                        cls._require_uuid(item["id"], "meter_values.id")

    def _build_request(self, action: str, params: Dict[str, Any]) -> Tuple[str, str, Any, Any]:
        if action == "query" or params.get("path"):
            return (
                str(params.get("method", "GET")).upper(),
                str(params["path"]),
                params.get("json"),
                params.get("query"),
            )
        qr_token = params.get("qr_token")
        if action == "check_qr":
            return "GET", "/api/v1/app/charging/check", None, {"qr_token": qr_token}
        if action == "start_charging":
            return "POST", "/api/v1/app/charging/start", {"qr_token": qr_token}, None
        if action == "get_active":
            return "GET", "/api/v1/app/charging/active", None, {"qr_token": qr_token}
        if action == "get_meter_values":
            return "GET", "/api/v1/app/charging/meter-values", None, params
        if action == "stop_charging":
            return "POST", "/api/v1/app/charging/stop", {"qr_token": qr_token}, None
        if action == "settle":
            return "POST", "/api/v1/app/charging/settle", {"session_id": params["session_id"]}, None
        if action == "get_wallet":
            return "GET", "/api/v1/app/wallet/balance", None, None
        if action == "get_history":
            return "GET", "/api/v1/app/transactions", None, params or None
        raise ValueError(f"Unsupported app action: {action}")
