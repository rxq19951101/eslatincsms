"""ChargingSession 领域服务。

所有协议事实写入在一个事务内完成，并对会话/EVSE 行加锁。SQLite 测试环境会忽略
FOR UPDATE，但生产 PostgreSQL 会使用该锁，唯一约束仍负责兜底并发创建。
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.id_generator import generate_order_id
from app.core.asset_identifiers import get_charge_point_by_reference, parse_uuid
from app.database.base import tenant_id_context
from app.database.models import ChargingSession, EVSE, EVSEStatus, Order, MeterValue
from app.domain.charging_session import validate_transition
from app.services.outbox_service import OutboxService
from app.services.asset_lifecycle_service import require_charge_point_operational

logger = logging.getLogger("ocpp_csms")


class SessionService:
    @staticmethod
    def start_session(
        db: Session,
        charge_point_id: str,
        evse_id: int,
        transaction_id: int,
        id_tag: str,
        user_id: Optional[str] = None,
        meter_start: int = 0,
    ) -> ChargingSession:
        charge_point = get_charge_point_by_reference(db, charge_point_id)
        if not charge_point:
            raise ValueError(f"Charge point not found: {charge_point_id}")
        evse = db.query(EVSE).filter(
            EVSE.charge_point_id == charge_point.id,
            EVSE.evse_id == evse_id,
        ).with_for_update().first()
        if not evse:
            raise ValueError(f"EVSE not found: charge_point_id={charge_point_id}, evse_id={evse_id}")

        tenant_id = tenant_id_context.get() or evse.tenant_id
        if not tenant_id:
            raise ValueError(f"Missing tenant_id for charge_point_id={charge_point_id}, evse_id={evse_id}")

        existing = db.query(ChargingSession).filter(
            ChargingSession.charge_point_id == charge_point.id,
            ChargingSession.evse_id == evse.id,
            ChargingSession.transaction_id == transaction_id,
        ).with_for_update().first()
        if existing:
            # StartTransaction 重放是幂等成功；不允许重新打开已结束会话。
            return existing

        # A connected device may race with retirement or site archival. The
        # protocol handler must not create a new session/order after either
        # lifecycle boundary has closed new business.
        require_charge_point_operational(charge_point)

        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.evse_id == evse.id
        ).with_for_update().first()
        if evse_status and evse_status.current_session_id:
            active = db.query(ChargingSession).filter(
                ChargingSession.id == evse_status.current_session_id
            ).with_for_update().first()
            if active and active.status == "ongoing":
                raise ValueError(f"EVSE already has an ongoing session: {active.id}")

        now = datetime.now(timezone.utc)
        session = ChargingSession(
            tenant_id=tenant_id,
            evse_id=evse.id,
            charge_point_id=charge_point.id,
            transaction_id=transaction_id,
            id_tag=id_tag,
            user_id=user_id,
            app_user_id=parse_uuid(user_id),
            start_time=now,
            meter_start=meter_start,
            status="ongoing",
        )
        db.add(session)
        db.flush()

        order_id = generate_order_id(charge_point_id=charge_point.ocpp_identity, transaction_id=transaction_id)
        db.add(Order(
            id=order_id,
            tenant_id=tenant_id,
            session_id=session.id,
            charge_point_id=charge_point.id,
            user_id=user_id or id_tag,
            app_user_id=parse_uuid(user_id),
            id_tag=id_tag,
            start_time=now,
            status="ongoing",
        ))

        if evse_status:
            evse_status.status = "Charging"
            evse_status.current_session_id = session.id
            evse_status.last_seen = now

        OutboxService.enqueue(
            db,
            tenant_id=tenant_id,
            aggregate_type="ChargingSession",
            aggregate_id=str(session.id),
            event_type="ChargingSessionStarted",
            idempotency_key=f"charging-session-started:{session.id}",
            payload={"session_id": str(session.id), "transaction_id": transaction_id, "charge_point_id": str(charge_point.id), "ocpp_identity": charge_point.ocpp_identity},
        )
        db.commit()
        db.refresh(session)
        logger.info("充电会话开始: session_id=%s, transaction_id=%s, order_id=%s", session.id, transaction_id, order_id)
        return session

    @staticmethod
    def stop_session(
        db: Session,
        charge_point_id: str,
        transaction_id: int,
        meter_stop: Optional[int] = None,
    ) -> Optional[ChargingSession]:
        charge_point = get_charge_point_by_reference(db, charge_point_id)
        if not charge_point:
            logger.warning("未找到充电桩: charge_point_id=%s", charge_point_id)
            return None
        session = db.query(ChargingSession).filter(
            ChargingSession.charge_point_id == charge_point.id,
            ChargingSession.transaction_id == transaction_id,
        ).with_for_update().first()
        if not session:
            logger.warning("未找到会话: charge_point_id=%s, transaction_id=%s", charge_point_id, transaction_id)
            return None

        if session.status != "ongoing":
            # StopTransaction 重复/断线重连：返回原会话，不重复结算或生成事件。
            return session

        validate_transition(session.status, "completed")
        now = datetime.now(timezone.utc)
        session.end_time = session.end_time or now
        if meter_stop is not None:
            session.meter_stop = meter_stop
        session.status = "completed"
        # Safety stop is independent of billing. An ended session that has not
        # already been paid remains collectible as unpaid after the device stop.
        if session.payment_status != "paid":
            session.payment_status = "unpaid"
        session.updated_at = now

        order = db.query(Order).filter(Order.session_id == session.id).with_for_update().first()
        if order:
            order.end_time = order.end_time or now
            order.status = "completed"
            order.updated_at = now

        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.current_session_id == session.id
        ).with_for_update().first()
        if evse_status:
            evse_status.status = "Available"
            evse_status.current_session_id = None
            evse_status.last_seen = now

        OutboxService.enqueue(
            db,
            tenant_id=session.tenant_id,
            aggregate_type="ChargingSession",
            aggregate_id=str(session.id),
            event_type="ChargingSessionCompleted",
            idempotency_key=f"charging-session-completed:{session.id}",
            payload={"session_id": str(session.id), "transaction_id": transaction_id, "meter_stop": meter_stop},
        )
        db.commit()
        db.refresh(session)
        logger.info("充电会话结束: session_id=%s, transaction_id=%s", session.id, transaction_id)
        return session

    @staticmethod
    def get_active_session(db: Session, charge_point_id: str, evse_id: Optional[int] = None) -> Optional[ChargingSession]:
        charge_point = get_charge_point_by_reference(db, charge_point_id)
        if not charge_point:
            return None
        query = db.query(ChargingSession).filter(
            ChargingSession.charge_point_id == charge_point.id,
            ChargingSession.status == "ongoing",
        )
        if evse_id:
            evse = db.query(EVSE).filter(
                EVSE.charge_point_id == charge_point.id,
                EVSE.evse_id == evse_id,
            ).first()
            if not evse:
                return None
            query = query.filter(ChargingSession.evse_id == evse.id)
        return query.with_for_update().first()

    @staticmethod
    def add_meter_value(
        db: Session,
        session_id: UUID,
        value: int,
        connector_id: Optional[int] = None,
        sampled_value: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        commit: bool = True,
    ) -> bool:
        session = db.query(ChargingSession).filter(
            ChargingSession.id == session_id
        ).with_for_update().first()
        if not session or session.status != "ongoing":
            return False
        if idempotency_key:
            existing = db.query(MeterValue).filter(
                MeterValue.session_id == session_id,
                MeterValue.idempotency_key == idempotency_key,
            ).first()
            if existing:
                return False

        tenant_id = tenant_id_context.get() or session.tenant_id
        if not tenant_id:
            return False
        db.add(MeterValue(
            tenant_id=tenant_id,
            session_id=session_id,
            connector_id=connector_id,
            idempotency_key=idempotency_key,
            timestamp=datetime.now(timezone.utc),
            value=int(value),
            sampled_value=sampled_value,
        ))
        if commit:
            db.commit()
        else:
            db.flush()
        return True
