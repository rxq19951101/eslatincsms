"""Redis-backed realtime MeterValues snapshots and persistence gating."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import redis
from redis.exceptions import RedisError

from app.core.config import get_settings


logger = logging.getLogger("ocpp_csms")


@dataclass(frozen=True)
class MeterTelemetryDecision:
    redis_available: bool
    duplicate: bool
    should_persist: bool
    dedupe_key: Optional[str] = None
    persist_gate_key: Optional[str] = None


class MeterTelemetryService:
    """Keep the hot telemetry path in Redis and gate minute DB samples."""

    _SCRIPT = """
local claimed = redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1])
if not claimed then
  return {0, 0}
end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
local persist = redis.call('SET', KEYS[3], ARGV[4], 'NX', 'EX', ARGV[5])
if persist then
  return {1, 1}
end
return {1, 0}
"""

    def __init__(self, redis_client=None):
        self._redis_client = redis_client
        self._client_initialized = redis_client is not None

    def _client(self):
        settings = get_settings()
        if settings.environment.lower() == "test" and not self._client_initialized:
            return None
        if not self._client_initialized:
            self._redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            self._client_initialized = True
        return self._redis_client

    @staticmethod
    def _prefix(tenant_id, session_id) -> str:
        return f"meter:{tenant_id}:{session_id}"

    def record_latest(
        self,
        *,
        tenant_id,
        session_id,
        message_key: str,
        snapshot: dict[str, Any],
    ) -> MeterTelemetryDecision:
        client = self._client()
        if client is None:
            return MeterTelemetryDecision(False, False, True)

        settings = get_settings()
        prefix = self._prefix(tenant_id, session_id)
        dedupe_key = f"{prefix}:message:{message_key}"
        latest_key = f"{prefix}:latest"
        gate_key = f"{prefix}:persist-gate"
        payload = json.dumps(snapshot, separators=(",", ":"), default=str)

        try:
            claimed, should_persist = client.eval(
                self._SCRIPT,
                3,
                dedupe_key,
                latest_key,
                gate_key,
                max(1, settings.meter_dedupe_ttl_seconds),
                payload,
                max(1, settings.meter_realtime_ttl_seconds),
                message_key,
                max(1, settings.meter_persist_interval_seconds),
            )
            return MeterTelemetryDecision(
                redis_available=True,
                duplicate=not bool(claimed),
                should_persist=bool(claimed and should_persist),
                dedupe_key=dedupe_key if claimed else None,
                persist_gate_key=gate_key if claimed and should_persist else None,
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            logger.warning("MeterValues Redis unavailable; using database fallback: %s", exc)
            return MeterTelemetryDecision(False, False, True)

    def release_write_claims(self, decision: MeterTelemetryDecision) -> None:
        keys = [
            key
            for key in (decision.dedupe_key, decision.persist_gate_key)
            if key
        ]
        if not keys:
            return
        client = self._client()
        if client is None:
            return
        try:
            client.delete(*keys)
        except (RedisError, OSError):
            logger.warning("Unable to release MeterValues write claims", exc_info=True)

    def get_latest(self, *, tenant_id, session_id) -> Optional[dict[str, Any]]:
        client = self._client()
        if client is None:
            return None
        try:
            raw = client.get(f"{self._prefix(tenant_id, session_id)}:latest")
            if not raw:
                return None
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except (RedisError, OSError, ValueError, TypeError):
            logger.warning("Unable to read realtime MeterValues snapshot", exc_info=True)
            return None


meter_telemetry_service = MeterTelemetryService()
