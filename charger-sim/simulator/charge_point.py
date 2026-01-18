from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as OcppChargePoint
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, AuthorizationStatus, RegistrationStatus

from .metering import MeteringState, advance_meter
from .profiles import ChargePointProfile, MeteringProfile

logger = logging.getLogger("eslatin_charger_sim")


@dataclass
class ConnectorRuntime:
    connector_id: int
    status: str = "Available"
    transaction_id: Optional[int] = None
    id_tag: Optional[str] = None
    meter: MeteringState = field(default_factory=MeteringState)
    metering_task: Optional[asyncio.Task] = None


@dataclass
class RuntimeState:
    connectors: Dict[int, ConnectorRuntime] = field(default_factory=dict)
    heartbeat_task: Optional[asyncio.Task] = None


class SimChargePoint(OcppChargePoint):
    """
    OCPP 1.6J 充电桩模拟器（WebSocket）
    - 按后端要求协商 ocpp1.6 子协议
    - 支持 RemoteStart/RemoteStop 驱动 Start/StopTransaction + MeterValues
    """

    def __init__(self, profile: ChargePointProfile, meterings: List[MeteringProfile], ws):
        super().__init__(profile.charge_point_id, ws)
        self.profile = profile
        self.state = RuntimeState()
        self.meterings: Dict[int, MeteringProfile] = {m.connector_id: m for m in meterings}
        # 初始化 connector runtime
        for cid in sorted(self.meterings.keys()):
            self.state.connectors[cid] = ConnectorRuntime(connector_id=cid)

    async def start_background(self) -> None:
        # Boot + 初始状态
        await self.send_boot_notification()
        # 每个 connector 发送一次状态
        for cid in sorted(self.state.connectors.keys()):
            await self.send_status_notification("Available", connector_id=cid)

        # Heartbeat loop
        self.state.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def shutdown(self) -> None:
        # 停止每个 connector 的 metering task
        for c in self.state.connectors.values():
            if c.metering_task and not c.metering_task.done():
                c.metering_task.cancel()
                try:
                    await c.metering_task
                except asyncio.CancelledError:
                    pass
        # 停止 heartbeat
        if self.state.heartbeat_task and not self.state.heartbeat_task.done():
            self.state.heartbeat_task.cancel()
            try:
                await self.state.heartbeat_task
            except asyncio.CancelledError:
                pass

    async def send_boot_notification(self) -> None:
        payload = call.BootNotificationPayload(
            charge_point_vendor=self.profile.vendor,
            charge_point_model=self.profile.model,
            charge_point_serial_number=self.profile.serial_number or self.profile.charge_point_id,
            firmware_version=self.profile.firmware_version,
        )
        res = await self.call(payload)
        status = getattr(res, "status", None)
        logger.info("[%s] BootNotification -> %s", self.id, status)
        if status != RegistrationStatus.accepted:
            logger.warning("[%s] BootNotification not accepted: %s", self.id, status)

    async def send_status_notification(self, status: str, connector_id: Optional[int] = None) -> None:
        cid = connector_id or 1
        if cid in self.state.connectors:
            self.state.connectors[cid].status = status
        payload = call.StatusNotificationPayload(
            connector_id=cid,
            error_code="NoError",
            status=status,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await self.call(payload)

    async def send_authorize(self, id_tag: str) -> bool:
        payload = call.AuthorizePayload(id_tag=id_tag)
        res = await self.call(payload)
        # ocpp lib 可能返回 dataclass 或 dict；这里做兼容
        try:
            info = getattr(res, "id_tag_info", None) or getattr(res, "idTagInfo", None) or {}
            status = info.get("status") if isinstance(info, dict) else getattr(info, "status", None)
            if status is None:
                return True
            return str(status) == str(AuthorizationStatus.accepted)
        except Exception:
            return True  # 认证失败也不阻塞模拟器流程（便于本地调试）

    async def send_start_transaction(self, id_tag: str, connector_id: int) -> int:
        if connector_id not in self.state.connectors:
            raise ValueError(f"Unsupported connector_id={connector_id}")
        c = self.state.connectors[connector_id]
        c.id_tag = id_tag
        payload = call.StartTransactionPayload(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=c.meter.meter_wh,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        res = await self.call(payload)
        tx = getattr(res, "transaction_id", None) or getattr(res, "transactionId", None)
        if tx is None and isinstance(res, dict):
            tx = res.get("transactionId") or res.get("transaction_id")
        if tx is None:
            raise RuntimeError(f"StartTransaction response missing transactionId: {res!r}")
        tx_id = int(tx)
        c.transaction_id = tx_id
        logger.info("[%s] StartTransaction accepted, connector=%s tx=%s", self.id, connector_id, tx_id)
        return tx_id

    async def send_stop_transaction(self, connector_id: int, reason: str = "Remote") -> None:
        if connector_id not in self.state.connectors:
            return
        c = self.state.connectors[connector_id]
        if c.transaction_id is None:
            return
        payload = call.StopTransactionPayload(
            transaction_id=c.transaction_id,
            meter_stop=c.meter.meter_wh,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason,
        )
        await self.call(payload)
        logger.info("[%s] StopTransaction sent, connector=%s tx=%s", self.id, connector_id, c.transaction_id)
        c.transaction_id = None
        c.id_tag = None

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.profile.heartbeat_interval_sec)
                await self.call(call.HeartbeatPayload())
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[%s] heartbeat failed: %s", self.id, e)

    async def _meter_values_loop(self, connector_id: int) -> None:
        if connector_id not in self.state.connectors:
            return
        c = self.state.connectors[connector_id]
        m = self.meterings.get(connector_id)
        if not m:
            return
        while c.transaction_id is not None:
            try:
                await asyncio.sleep(m.meter_values_interval_sec)
                advance_meter(
                    c.meter,
                    interval_sec=m.meter_values_interval_sec,
                    power_kw=m.power_kw,
                    soc_end=m.soc_end,
                )

                mv = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {"measurand": "Energy.Active.Import.Register", "value": str(c.meter.meter_wh), "unit": "Wh"},
                        {"measurand": "Power.Active.Import", "value": str(int(m.power_kw * 1000)), "unit": "W"},
                        {"measurand": "Current.Import", "value": str(m.current_a), "unit": "A"},
                        {"measurand": "Voltage", "value": str(m.voltage_v), "unit": "V"},
                        {"measurand": "SoC", "value": str(int(c.meter.soc)), "unit": "Percent"},
                    ],
                }

                payload = call.MeterValuesPayload(
                    connector_id=connector_id,
                    transaction_id=c.transaction_id,
                    meter_value=[mv],
                )
                await self.call(payload)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[%s] MeterValues failed (connector=%s): %s", self.id, connector_id, e)

    # ---------- CSMS -> CP handlers ----------

    @on(Action.RemoteStartTransaction)
    async def on_remote_start(self, id_tag: str, connector_id: Optional[int] = None, **kwargs):
        logger.info("[%s] <- RemoteStartTransaction id_tag=%s connector_id=%s", self.id, id_tag, connector_id)
        if connector_id is None:
            return call_result.RemoteStartTransactionPayload(status="Rejected")
        if connector_id not in self.state.connectors:
            return call_result.RemoteStartTransactionPayload(status="Rejected")

        c = self.state.connectors[connector_id]
        if c.transaction_id is not None:
            # 已在充电中
            return call_result.RemoteStartTransactionPayload(status="Rejected")

        # RemoteStartTransaction 的 CALLRESULT 应尽快返回，否则 CSMS 侧会超时。
        # 因此把“授权/启动事务/状态切换/开始抄表”的重活放到后台任务里执行。
        async def _run_start_flow() -> None:
            try:
                await self.send_status_notification("Preparing", connector_id=connector_id)
                await self.send_authorize(id_tag)
                await self.send_start_transaction(id_tag, connector_id=connector_id)
                await self.send_status_notification("Charging", connector_id=connector_id)

                # Start metering loop
                if c.metering_task and not c.metering_task.done():
                    c.metering_task.cancel()
                c.metering_task = asyncio.create_task(self._meter_values_loop(connector_id=connector_id))
            except Exception as e:
                logger.error("[%s] remote start flow failed: %s", self.id, e)

        asyncio.create_task(_run_start_flow())

        return call_result.RemoteStartTransactionPayload(status="Accepted")

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop(self, transaction_id: int, **kwargs):
        logger.info("[%s] <- RemoteStopTransaction transaction_id=%s", self.id, transaction_id)

        # 找到对应 connector
        target: Optional[Tuple[int, ConnectorRuntime]] = None
        for cid, c in self.state.connectors.items():
            if c.transaction_id == transaction_id:
                target = (cid, c)
                break

        # RemoteStopTransaction 的 CALLRESULT 也应尽快返回，否则 CSMS 侧会超时并把停止操作判定为失败。
        # 所以把 StopTransaction/状态切换 放到后台任务。
        async def _run_stop_flow() -> None:
            try:
                if target:
                    cid, c = target
                    if c.metering_task and not c.metering_task.done():
                        c.metering_task.cancel()
                    await self.send_stop_transaction(connector_id=cid, reason="Remote")
                    await self.send_status_notification("Available", connector_id=cid)
            except Exception as e:
                logger.error("[%s] remote stop flow failed: %s", self.id, e)

        asyncio.create_task(_run_stop_flow())

        return call_result.RemoteStopTransactionPayload(status="Accepted")


async def connect_and_run(profile: ChargePointProfile, meterings: List[MeteringProfile], ws_base: str) -> None:
    url = f"{ws_base}?id={profile.charge_point_id}"
    logger.info("[%s] connecting %s", profile.charge_point_id, url)
    async with websockets.connect(url, subprotocols=["ocpp1.6"]) as ws:
        # CSMS 侧会在连接建立后发送一条非 OCPP 标准的 “Connected” JSON（用于调试）。
        # ocpp 库的 listener 只能处理 OCPP 1.6 的数组消息格式，若直接进入 cp.start() 会因解析失败而断开。
        # 因此这里先吞掉这条欢迎消息（如果存在）。
        try:
            hello = await asyncio.wait_for(ws.recv(), timeout=2)
            if isinstance(hello, str) and hello.lstrip().startswith("{"):
                logger.debug("[%s] ignored non-ocpp greeting: %s", profile.charge_point_id, hello[:200])
            else:
                # 如果不是该欢迎消息，则不再额外处理（避免误吞合法 OCPP 数据）
                logger.debug("[%s] first message not greeting, ignoring peek", profile.charge_point_id)
        except asyncio.TimeoutError:
            # 某些环境不会发欢迎消息，超时即可
            pass

        cp = SimChargePoint(profile=profile, meterings=meterings, ws=ws)
        # 必须先启动 listener，才能让 cp.call() 收到 CALLRESULT/CALLERROR
        listener_task = asyncio.create_task(cp.start())
        try:
            await cp.start_background()
            await listener_task  # listen forever
        finally:
            if not listener_task.done():
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass
            await cp.shutdown()

