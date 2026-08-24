from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any, Dict, List
from urllib.parse import urlsplit

import httpx

from simulator.payment_simulator import VALID_PAYMENT_STATUSES, require_session_uuid

from .base import ActorResult, BaseActor


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "csms", "host.docker.internal"}


class FakePaymentActor(BaseActor):
    def __init__(self, name: str, config: Dict[str, Any], run_id: str):
        super().__init__(name, config, run_id)
        self.events: Dict[str, Dict[str, str]] = {}
        self.client = httpx.AsyncClient(timeout=float(config.get("timeout", 10)))

    async def execute(self, action: str, params: Dict[str, Any], step_id: str) -> ActorResult:
        if action != "emit_webhook":
            raise ValueError(f"Unsupported fake payment action: {action}")
        webhook_path = params.get("path") or self.config.get("webhook_path")
        if not webhook_path:
            raise RuntimeError(
                "fake payment webhook_path is required; synthetic success is forbidden"
            )

        target_environment = str(self.config.get("environment", "")).lower()
        if target_environment not in {"development", "test"}:
            raise ValueError("fake payment actor requires environment=development or test")

        base_url = str(self.config.get("base_url", "http://csms:9000")).rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_HOSTS:
            raise ValueError("fake payment actor may call only an explicitly configured local CSMS API")
        if not str(webhook_path).startswith("/"):
            raise ValueError("fake payment webhook_path must be an absolute API path")
        url = f"{base_url}{webhook_path}"

        secret = self.config.get("webhook_secret")
        if not secret:
            raise RuntimeError("SIM_E2E_WEBHOOK_SECRET is required for fake payment delivery")

        session_id = params.get("session_id")
        payment_order_id = params.get("payment_order_id")
        if (session_id is None) == (payment_order_id is None):
            raise ValueError("exactly one of session_id or payment_order_id is required")
        resource: Dict[str, str]
        if session_id is not None:
            resource = {"session_id": require_session_uuid(str(session_id))}
        else:
            try:
                canonical_order_id = str(uuid.UUID(str(payment_order_id)))
            except (ValueError, AttributeError) as exc:
                raise ValueError("payment_order_id must be a UUID string") from exc
            resource = {"payment_order_id": canonical_order_id}

        statuses = params.get("statuses") or [params.get("status", "approved")]
        if not isinstance(statuses, list) or not statuses:
            raise ValueError("statuses must be a non-empty list")
        statuses = [str(status) for status in statuses]
        unsupported = [status for status in statuses if status not in VALID_PAYMENT_STATUSES]
        if unsupported:
            raise ValueError(f"Unsupported fake payment status: {unsupported[0]}")
        duplicate = int(params.get("duplicate", 1))
        if duplicate < 1 or duplicate > 10:
            raise ValueError("duplicate must be between 1 and 10")

        base_event_id = str(params.get("event_id") or f"{self.run_id}:{step_id}")
        deliveries: List[Dict[str, Any]] = []
        requests: List[Dict[str, Any]] = []
        first_failure: int | None = None
        last_status = 0
        for status_index, status in enumerate(statuses):
            event_id = base_event_id if len(statuses) == 1 else f"{base_event_id}:{status_index + 1}"
            event = {
                "event_id": event_id,
                "provider": "fake",
                "status": status,
                **resource,
            }
            self.events[event_id] = event
            raw_body = json.dumps(
                event,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
            for copy_index in range(duplicate):
                signature = hmac.new(
                    str(secret).encode("utf-8"), raw_body, hashlib.sha256
                ).hexdigest()
                headers = {
                    "Content-Type": "application/json",
                    "Idempotency-Key": event_id,
                    "X-Sim-Signature": f"sha256={signature}",
                }
                response = await self.client.post(url, content=raw_body, headers=headers)
                try:
                    response_body = response.json()
                except ValueError:
                    response_body = {"text": response.text}
                last_status = response.status_code
                if response.status_code >= 400 and first_failure is None:
                    first_failure = response.status_code
                deliveries.append(
                    {
                        "event_id": event_id,
                        "event_status": status,
                        "copy": copy_index + 1,
                        "status_code": response.status_code,
                        "response": response_body,
                    }
                )
                requests.append(
                    {"method": "POST", "url": url, "json": event, "headers": headers}
                )
        return ActorResult(
            status=first_failure or last_status,
            body={
                "provider": "fake",
                "network": True,
                "delivery_count": len(deliveries),
                "deliveries": deliveries,
            },
            request={"deliveries": requests},
            response={"deliveries": deliveries},
        )

    async def close(self) -> None:
        await self.client.aclose()
