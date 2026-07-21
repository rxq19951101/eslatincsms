"""Compatibility facade for the local fake payment provider.

This module intentionally has no third-party payment SDK or Internet endpoint. Scenario
tests should use :class:`actors.fake_payment.FakePaymentActor` directly.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, Optional


VALID_PAYMENT_STATUSES = {"approved", "pending", "rejected", "timeout"}


def require_session_uuid(session_id: str) -> str:
    """Keep internal session UUIDs distinct from integer OCPP transaction IDs."""
    if not isinstance(session_id, str):
        raise TypeError("session_id must be a UUID string, never an OCPP transaction_id")
    try:
        return str(uuid.UUID(session_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError("session_id must be a valid UUID string") from exc


async def get_session_id_by_transaction(*args: Any, **kwargs: Any) -> Optional[str]:
    """Refuse the legacy transaction-id-as-session-id shortcut."""
    raise RuntimeError(
        "A session UUID must be obtained from the App active-session API; "
        "an OCPP transaction_id cannot be used as session_id"
    )


async def simulate_charging_payment(
    session_id: str,
    amount: float,
    charge_point_id: str,
    backend_api_url: Optional[str] = None,
    test_card_name: str = "approved",
    payment_delay_seconds: int = 0,
    backend_token: Optional[str] = None,
    *,
    status: Optional[str] = None,
) -> bool:
    """Produce an in-process fake result without calling a payment network.

    ``backend_api_url`` and ``backend_token`` remain accepted only for legacy callers;
    they are deliberately ignored. Use the scenario fake-payment actor to emit a local
    webhook through an explicitly configured test API.
    """
    del amount, charge_point_id, backend_api_url, backend_token
    require_session_uuid(session_id)
    selected = status or test_card_name
    if selected not in VALID_PAYMENT_STATUSES:
        raise ValueError(f"Unsupported fake payment status: {selected}")
    if payment_delay_seconds > 0:
        await asyncio.sleep(payment_delay_seconds)
    return selected == "approved"


def fake_payment_event(session_id: str, status: str, event_id: Optional[str] = None) -> Dict[str, str]:
    """Build deterministic fake-provider webhook data for API actor use."""
    canonical_session_id = require_session_uuid(session_id)
    if status not in VALID_PAYMENT_STATUSES:
        raise ValueError(f"Unsupported fake payment status: {status}")
    return {
        "event_id": event_id or f"fake-{uuid.uuid4()}",
        "provider": "fake",
        "session_id": canonical_session_id,
        "status": status,
    }
