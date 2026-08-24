from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as OcppChargePoint
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, AuthorizationStatus, RegistrationStatus

from .metering import MeteringState, advance_meter, allocate_shared_power_kw
from .profiles import ChargePointProfile, MeteringProfile
logger = logging.getLogger("eslatin_charger_sim")


def build_websocket_url(ws_base: str, ocpp_identity: str) -> str:
    """Build either /ocpp?id=IDENTITY or /ocpp/{identity}."""
    if "{identity}" in ws_base:
        from urllib.parse import quote
        return ws_base.replace("{identity}", quote(ocpp_identity, safe="._:-"))
    parts = urlsplit(ws_base)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "id"]
    query.append(("id", ocpp_identity))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_auth_headers(ocpp_identity: str, secret: Optional[str]) -> Dict[str, str]:
    if not secret:
        return {}
    value = base64.b64encode(f"{ocpp_identity}:{secret}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {value}"}


@dataclass
class ConnectorRuntime:
    connector_id: int
    status: str = "Available"
    transaction_id: Optional[int] = None
    id_tag: Optional[str] = None
    meter: MeteringState = field(default_factory=MeteringState)
    metering_task: Optional[asyncio.Task] = None
    start_pending: bool = False


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
        super().__init__(profile.ocpp_identity, ws)
        self.profile = profile
        self.state = RuntimeState()
        self.meterings: Dict[int, MeteringProfile] = {m.connector_id: m for m in meterings}
        self.configuration: Dict[str, str] = {
            "HeartbeatInterval": str(profile.heartbeat_interval_sec),
            "MeterValueSampleInterval": str(
                min((m.meter_values_interval_sec for m in meterings), default=5)
            ),
        }
        self.received_commands: List[Dict[str, Any]] = []
        # 初始化 connector runtime
        for cid in sorted(self.meterings.keys()):
            self.state.connectors[cid] = ConnectorRuntime(connector_id=cid)

    def allocated_power_kw(self, connector_id: int) -> float:
        """Return the connector's current power after applying a shared limit."""
        metering = self.meterings.get(connector_id)
        if metering is None:
            raise ValueError(f"Missing metering profile for connector_id={connector_id}")
        if self.profile.shared_power_limit_kw is None:
            return metering.power_kw

        active_connector_ids = [
            cid
            for cid, runtime in self.state.connectors.items()
            if runtime.transaction_id is not None
        ]
        allocations = allocate_shared_power_kw(
            {cid: item.power_kw for cid, item in self.meterings.items()},
            active_connector_ids,
            self.profile.shared_power_limit_kw,
        )
        return allocations.get(connector_id, 0.0)

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

    async def send_boot_notification(self):
        payload = call.BootNotificationPayload(
            charge_point_vendor=self.profile.vendor,
            charge_point_model=self.profile.model,
            charge_point_serial_number=self.profile.boot_serial_number,
            firmware_version=self.profile.firmware_version,
        )
        res = await self.call(payload)
        status = getattr(res, "status", None)
        logger.info("[%s] BootNotification -> %s", self.id, status)
        if status != RegistrationStatus.accepted:
            logger.warning("[%s] BootNotification not accepted: %s", self.id, status)
        return status

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
            if isinstance(res, dict):
                info = res.get("id_tag_info") or res.get("idTagInfo") or {}
            else:
                info = getattr(res, "id_tag_info", None) or getattr(res, "idTagInfo", None) or {}
            status = info.get("status") if isinstance(info, dict) else getattr(info, "status", None)
            if status is None:
                return False
            status_value = getattr(status, "value", status)
            accepted_value = getattr(
                AuthorizationStatus.accepted,
                "value",
                AuthorizationStatus.accepted,
            )
            return str(status_value).strip().casefold() == str(accepted_value).strip().casefold()
        except Exception as exc:
            logger.warning("[%s] Authorize response could not be parsed: %s", self.id, exc)
            return False

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

    async def send_stop_transaction(self, connector_id: int, reason: str = "Remote") -> bool:
        if connector_id not in self.state.connectors:
            return False
        c = self.state.connectors[connector_id]
        if c.transaction_id is None:
            return False
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
        return True

    async def send_heartbeat(self):
        return await self.call(call.HeartbeatPayload())

    async def send_meter_values(self, connector_id: int, *, advance: bool = True):
        if connector_id not in self.state.connectors:
            raise ValueError(f"Unsupported connector_id={connector_id}")
        connector = self.state.connectors[connector_id]
        metering = self.meterings.get(connector_id)
        if metering is None:
            raise ValueError(f"Missing metering profile for connector_id={connector_id}")
        if connector.transaction_id is None:
            raise RuntimeError("MeterValues requires an active OCPP transaction")
        allocated_power_kw = self.allocated_power_kw(connector_id)
        if advance:
            advance_meter(
                connector.meter,
                interval_sec=metering.meter_values_interval_sec,
                power_kw=allocated_power_kw,
                soc_end=metering.soc_end,
            )
        sampled_value = [
            {
                "measurand": "Energy.Active.Import.Register",
                "value": str(connector.meter.meter_wh),
                "unit": "Wh",
            },
            {
                "measurand": "Power.Active.Import",
                "value": str(int(allocated_power_kw * 1000)),
                "unit": "W",
            },
            {"measurand": "Current.Import", "value": str(metering.current_a), "unit": "A"},
            {"measurand": "Voltage", "value": str(metering.voltage_v), "unit": "V"},
            {"measurand": "SoC", "value": str(int(connector.meter.soc)), "unit": "Percent"},
        ]
        payload = call.MeterValuesPayload(
            connector_id=connector_id,
            transaction_id=connector.transaction_id,
            meter_value=[
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": sampled_value,
                }
            ],
        )
        return await self.call(payload)

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.profile.heartbeat_interval_sec)
                await self.send_heartbeat()
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
                await self.send_meter_values(connector_id)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[%s] MeterValues failed (connector=%s): %s", self.id, connector_id, e)

    # ---------- CSMS -> CP handlers ----------

    def _record_command(self, action: str, status: str, **details: Any) -> None:
        self.received_commands.append(
            {
                "sequence": len(self.received_commands) + 1,
                "action": action,
                "status": status,
                "received_at": datetime.now(timezone.utc).isoformat(),
                **details,
            }
        )

    @on(Action.RemoteStartTransaction)
    async def on_remote_start(self, id_tag: str, connector_id: Optional[int] = None, **kwargs):
        logger.info("[%s] <- RemoteStartTransaction id_tag=%s connector_id=%s", self.id, id_tag, connector_id)
        if connector_id is None:
            self._record_command("RemoteStartTransaction", "Rejected", connector_id=None)
            return call_result.RemoteStartTransactionPayload(status="Rejected")
        if connector_id not in self.state.connectors:
            self._record_command("RemoteStartTransaction", "Rejected", connector_id=connector_id)
            return call_result.RemoteStartTransactionPayload(status="Rejected")

        c = self.state.connectors[connector_id]
        if c.transaction_id is not None or c.start_pending:
            # 已在充电中
            self._record_command("RemoteStartTransaction", "Rejected", connector_id=connector_id)
            return call_result.RemoteStartTransactionPayload(status="Rejected")
        c.start_pending = True

        # RemoteStartTransaction 的 CALLRESULT 应尽快返回，否则 CSMS 侧会超时。
        # 因此把“授权/启动事务/状态切换/开始抄表”的重活放到后台任务里执行。
        async def _run_start_flow() -> None:
            try:
                await self.send_status_notification("Preparing", connector_id=connector_id)
                authorized = await self.send_authorize(id_tag)
                if not authorized:
                    logger.warning("[%s] Authorize rejected; StartTransaction aborted", self.id)
                    await self.send_status_notification("Available", connector_id=connector_id)
                    return
                tx_id = await self.send_start_transaction(id_tag, connector_id=connector_id)
                await self.send_status_notification("Charging", connector_id=connector_id)

                # Start metering loop
                if c.metering_task and not c.metering_task.done():
                    c.metering_task.cancel()
                c.metering_task = asyncio.create_task(self._meter_values_loop(connector_id=connector_id))
                
            except Exception as e:
                logger.error("[%s] remote start flow failed: %s", self.id, e)
            finally:
                c.start_pending = False

        asyncio.create_task(_run_start_flow())

        self._record_command("RemoteStartTransaction", "Accepted", connector_id=connector_id)
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

        if target is None:
            self._record_command("RemoteStopTransaction", "Rejected", transaction_id=transaction_id)
            return call_result.RemoteStopTransactionPayload(status="Rejected")

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

        self._record_command("RemoteStopTransaction", "Accepted", transaction_id=transaction_id)
        return call_result.RemoteStopTransactionPayload(status="Accepted")

    @on(Action.Reset)
    async def on_reset(self, type: str, **kwargs):
        if type not in {"Soft", "Hard"}:
            self._record_command("Reset", "Rejected", reset_type=type)
            return call_result.ResetPayload(status="Rejected")
        for connector in self.state.connectors.values():
            connector.start_pending = False
            connector.transaction_id = None
            connector.id_tag = None
        self._record_command("Reset", "Accepted", reset_type=type)
        return call_result.ResetPayload(status="Accepted")

    @on(Action.GetConfiguration)
    async def on_get_configuration(self, key: Optional[List[str]] = None, **kwargs):
        selected = key or sorted(self.configuration)
        configuration_key = [
            {"key": item, "readonly": False, "value": self.configuration[item]}
            for item in selected
            if item in self.configuration
        ]
        unknown_key = [item for item in selected if item not in self.configuration]
        self._record_command("GetConfiguration", "Accepted", keys=selected)
        return call_result.GetConfigurationPayload(
            configuration_key=configuration_key,
            unknown_key=unknown_key,
        )

    @on(Action.ChangeConfiguration)
    async def on_change_configuration(self, key: str, value: str, **kwargs):
        self.configuration[key] = value
        self._record_command("ChangeConfiguration", "Accepted", key=key)
        return call_result.ChangeConfigurationPayload(status="Accepted")

    @on(Action.UnlockConnector)
    async def on_unlock_connector(self, connector_id: int, **kwargs):
        connector = self.state.connectors.get(connector_id)
        status = "Unlocked" if connector is not None and connector.transaction_id is None else "UnlockFailed"
        self._record_command("UnlockConnector", status, connector_id=connector_id)
        return call_result.UnlockConnectorPayload(status=status)


async def connect_and_run(
    profile: ChargePointProfile,
    meterings: List[MeteringProfile],
    ws_base: str,
    runtime_holder: Optional[Dict[str, Any]] = None,
    ready_event: Optional[asyncio.Event] = None,
    ocpp_secret: Optional[str] = None,
) -> None:
    url = build_websocket_url(ws_base, profile.ocpp_identity)
    logger.info(
        "[%s] connecting %s (BootNotification serial=%s)",
        profile.ocpp_identity,
        url,
        profile.boot_serial_number,
    )
    async with websockets.connect(
        url,
        subprotocols=["ocpp1.6"],
        extra_headers=build_auth_headers(profile.ocpp_identity, ocpp_secret),
    ) as ws:
        cp = SimChargePoint(profile=profile, meterings=meterings, ws=ws)
        if runtime_holder is not None:
            runtime_holder["charge_point"] = cp
        # 必须先启动 listener，才能让 cp.call() 收到 CALLRESULT/CALLERROR
        listener_task = asyncio.create_task(cp.start())
        try:
            await cp.start_background()
            if ready_event is not None:
                ready_event.set()
            await listener_task  # listen forever
        finally:
            if not listener_task.done():
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass
            await cp.shutdown()
