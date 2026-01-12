from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as OcppChargePoint
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, AuthorizationStatus, RegistrationStatus
from ocpp.v16.datatypes import MeterValue as OcppMeterValue, SampledValue as OcppSampledValue

from .metering import MeteringState, advance_meter
from .profiles import ChargePointProfile, MeteringProfile

logger = logging.getLogger("eslatin_charger_sim")


@dataclass
class RuntimeState:
    status: str = "Available"
    transaction_id: Optional[int] = None
    id_tag: Optional[str] = None
    meter: MeteringState = MeteringState()
    metering_task: Optional[asyncio.Task] = None
    heartbeat_task: Optional[asyncio.Task] = None


class SimChargePoint(OcppChargePoint):
    """
    OCPP 1.6J 充电桩模拟器（WebSocket）
    - 按后端要求协商 ocpp1.6 子协议
    - 支持 RemoteStart/RemoteStop 驱动 Start/StopTransaction + MeterValues
    """

    def __init__(self, profile: ChargePointProfile, metering: MeteringProfile, ws):
        super().__init__(profile.charge_point_id, ws)
        self.profile = profile
        self.metering = metering
        self.state = RuntimeState()

    async def start_background(self) -> None:
        # Boot + 初始状态
        await self.send_boot_notification()
        await self.send_status_notification("Available")

        # Heartbeat loop
        self.state.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def shutdown(self) -> None:
        for t in [self.state.metering_task, self.state.heartbeat_task]:
            if t and not t.done():
                t.cancel()
                try:
                    await t
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
        self.state.status = status
        payload = call.StatusNotificationPayload(
            connector_id=connector_id or self.metering.connector_id,
            error_code="NoError",
            status=status,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await self.call(payload)

    async def send_authorize(self, id_tag: str) -> bool:
        payload = call.AuthorizePayload(id_tag=id_tag)
        res = await self.call(payload)
        try:
            return res.id_tag_info["status"] == AuthorizationStatus.accepted
        except Exception:
            return True

    async def send_start_transaction(self, id_tag: str) -> int:
        self.state.id_tag = id_tag
        payload = call.StartTransactionPayload(
            connector_id=self.metering.connector_id,
            id_tag=id_tag,
            meter_start=self.state.meter.meter_wh,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        res = await self.call(payload)
        tx_id = int(getattr(res, "transaction_id", None) or getattr(res, "transactionId", None) or res["transactionId"])
        self.state.transaction_id = tx_id
        logger.info("[%s] StartTransaction accepted, tx=%s", self.id, tx_id)
        return tx_id

    async def send_stop_transaction(self, reason: str = "Remote") -> None:
        if self.state.transaction_id is None:
            return
        payload = call.StopTransactionPayload(
            transaction_id=self.state.transaction_id,
            meter_stop=self.state.meter.meter_wh,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason,
        )
        await self.call(payload)
        logger.info("[%s] StopTransaction sent, tx=%s", self.id, self.state.transaction_id)
        self.state.transaction_id = None
        self.state.id_tag = None

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.profile.heartbeat_interval_sec)
                await self.call(call.HeartbeatPayload())
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[%s] heartbeat failed: %s", self.id, e)

    async def _meter_values_loop(self) -> None:
        while self.state.transaction_id is not None:
            try:
                await asyncio.sleep(self.metering.meter_values_interval_sec)
                advance_meter(
                    self.state.meter,
                    interval_sec=self.metering.meter_values_interval_sec,
                    power_kw=self.metering.power_kw,
                    soc_end=self.metering.soc_end,
                )

                # OCPP sampledValue：后端会解析 measurand=Energy.Active.Import.Register（Wh）
                sampled = [
                    OcppSampledValue(
                        value=str(self.state.meter.meter_wh),
                        measurand="Energy.Active.Import.Register",
                        unit="Wh",
                    ),
                    OcppSampledValue(
                        value=str(int(self.metering.power_kw * 1000)),
                        measurand="Power.Active.Import",
                        unit="W",
                    ),
                    OcppSampledValue(
                        value=str(self.metering.current_a),
                        measurand="Current.Import",
                        unit="A",
                    ),
                    OcppSampledValue(
                        value=str(self.metering.voltage_v),
                        measurand="Voltage",
                        unit="V",
                    ),
                    OcppSampledValue(
                        value=str(int(self.state.meter.soc)),
                        measurand="SoC",
                        unit="Percent",
                    ),
                ]

                mv = OcppMeterValue(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    sampled_value=sampled,
                )

                payload = call.MeterValuesPayload(
                    connector_id=self.metering.connector_id,
                    transaction_id=self.state.transaction_id,
                    meter_value=[mv],
                )
                await self.call(payload)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[%s] MeterValues failed: %s", self.id, e)

    # ---------- CSMS -> CP handlers ----------

    @on(Action.RemoteStartTransaction)
    async def on_remote_start(self, id_tag: str, connector_id: Optional[int] = None, **kwargs):
        # connector_id: CSMS may send; we accept but keep our configured connector
        logger.info("[%s] <- RemoteStartTransaction id_tag=%s connector_id=%s", self.id, id_tag, connector_id)

        # Authorize (optional, backend accepts mostly)
        try:
            await self.send_status_notification("Preparing")
            await self.send_authorize(id_tag)
            await self.send_start_transaction(id_tag)
            await self.send_status_notification("Charging")

            # Start metering loop
            if self.state.metering_task and not self.state.metering_task.done():
                self.state.metering_task.cancel()
            self.state.metering_task = asyncio.create_task(self._meter_values_loop())
        except Exception as e:
            logger.error("[%s] remote start flow failed: %s", self.id, e)

        return call_result.RemoteStartTransactionPayload(status="Accepted")

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop(self, transaction_id: int, **kwargs):
        logger.info("[%s] <- RemoteStopTransaction transaction_id=%s", self.id, transaction_id)

        # Stop metering first
        if self.state.metering_task and not self.state.metering_task.done():
            self.state.metering_task.cancel()

        try:
            await self.send_stop_transaction(reason="Remote")
            await self.send_status_notification("Available")
        except Exception as e:
            logger.error("[%s] remote stop flow failed: %s", self.id, e)

        return call_result.RemoteStopTransactionPayload(status="Accepted")


async def connect_and_run(profile: ChargePointProfile, metering: MeteringProfile, ws_base: str) -> None:
    url = f"{ws_base}?id={profile.charge_point_id}"
    logger.info("[%s] connecting %s", profile.charge_point_id, url)
    async with websockets.connect(url, subprotocols=["ocpp1.6"]) as ws:
        cp = SimChargePoint(profile=profile, metering=metering, ws=ws)
        await cp.start_background()
        try:
            await cp.start()  # listen forever
        finally:
            await cp.shutdown()

