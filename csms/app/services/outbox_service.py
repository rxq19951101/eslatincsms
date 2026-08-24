import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import OutboxEvent

logger = logging.getLogger("ocpp_csms")


class OutboxService:
    @staticmethod
    def enqueue(
        db: Session,
        *,
        tenant_id,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        idempotency_key: str,
        payload: Any,
    ) -> OutboxEvent:
        existing = db.query(OutboxEvent).filter(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return existing
        event = OutboxEvent(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            event_type=event_type,
            idempotency_key=idempotency_key,
            payload=payload,
            status="pending",
            attempts=0,
            available_at=datetime.now(timezone.utc),
        )
        db.add(event)
        return event

