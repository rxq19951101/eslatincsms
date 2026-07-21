from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

import websockets
from ocpp.v16.enums import RegistrationStatus

from faults.injection import duplicate_frames, meter_before_start_frame, stop_before_start_frame
from protocol.ocpp16.frames import build_call, encode_frame, validate_frame
from protocol.ocpp16.state import DevicePhase, DeviceState
from simulator.charge_point import SimChargePoint, build_auth_headers, build_websocket_url
from simulator.profiles import ChargePointProfile, MeteringProfile

from .base import ActorResult, BaseActor


def _response_body(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (str, int, float, bool, dict, list)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return str(value)


class ChargerActor(BaseActor):
    def __init__(self, name: str, config: Dict[str, Any], run_id: str):
        super().__init__(name, config, run_id)
        self.ws = None
        self.charge_point: Optional[SimChargePoint] = None
        self.listener_task: Optional[asyncio.Task] = None
        self.device_state = DeviceState()
        self.last_frame: Optional[List[Any]] = None

    def _profile(self) -> ChargePointProfile:
        return ChargePointProfile(
            charge_point_id=str(self.config["ocpp_identity"]),
            serial_number=self.config.get("serial_number"),
            vendor=str(self.config.get("vendor", "EsLatin")),
            model=str(self.config.get("model", "EsLatin-Scenario-1.0")),
            firmware_version=str(self.config.get("firmware_version", "1.0.0")),
            heartbeat_interval_sec=int(self.config.get("heartbeat_interval", 30)),
            enable_payment_simulation=False,
        )

    def _meterings(self) -> List[MeteringProfile]:
        connector_ids = self.config.get("connector_ids") or [self.config.get("connector_id", 1)]
        return [
            MeteringProfile(
                connector_id=int(connector_id),
                power_kw=float(self.config.get("power_kw", 7.0)),
                meter_values_interval_sec=int(self.config.get("meter_interval", 5)),
            )
            for connector_id in connector_ids
        ]

    def _require_connected(self) -> SimChargePoint:
        if self.charge_point is None or self.ws is None:
            raise RuntimeError("charger actor is not connected")
        return self.charge_point

    async def connect(self, ocpp_secret: Optional[str] = None) -> ActorResult:
        if self.ws is not None:
            raise RuntimeError("charger actor is already connected")
        profile = self._profile()
        url = build_websocket_url(str(self.config["ws"]), profile.ocpp_identity)
        self.ws = await websockets.connect(
            url,
            subprotocols=["ocpp1.6"],
            extra_headers=build_auth_headers(
                profile.ocpp_identity,
                ocpp_secret or self.config.get("ocpp_secret"),
            ),
        )
        self.charge_point = SimChargePoint(profile, self._meterings(), self.ws)
        self.listener_task = asyncio.create_task(self.charge_point.start())
        self.device_state.connect()
        return ActorResult(status="connected", body={"ocpp_identity": profile.ocpp_identity}, request={"url": url})

    async def disconnect(self) -> ActorResult:
        if self.charge_point is not None:
            await self.charge_point.shutdown()
        if self.listener_task is not None and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
        if self.ws is not None:
            await self.ws.close()
        self.ws = None
        self.charge_point = None
        self.listener_task = None
        self.device_state.disconnect()
        return ActorResult(status="disconnected", body={})

    async def send_frame(self, frame: List[Any]) -> ActorResult:
        self._require_connected()
        validated = validate_frame(frame)
        await self.ws.send(encode_frame(validated))
        self.last_frame = list(validated)
        return ActorResult(status="sent", body={"unique_id": validated[1]}, frame=validated)

    async def execute(self, action: str, params: Dict[str, Any], step_id: str) -> ActorResult:
        del step_id
        if action == "connect":
            if params.get("ocpp_secret"):
                self.config["ocpp_secret"] = params["ocpp_secret"]
            return await self.connect(params.get("ocpp_secret"))
        if action == "disconnect":
            return await self.disconnect()
        if action == "reconnect":
            await self.disconnect()
            delay = float(params.get("delay", 0))
            if delay:
                await asyncio.sleep(delay)
            return await self.connect(self.config.get("ocpp_secret"))

        cp = self._require_connected()
        if action == "boot":
            status = await cp.send_boot_notification()
            accepted = status == RegistrationStatus.accepted or str(status) == "Accepted"
            self.device_state.boot(accepted)
            return ActorResult(status=str(status), body={"accepted": accepted})
        if action in {"status", "faulted"}:
            status = "Faulted" if action == "faulted" else str(params.get("status", "Available"))
            connector_id = int(params.get("connector_id", 1))
            await cp.send_status_notification(status, connector_id=connector_id)
            if status == "Faulted":
                self.device_state.fault()
            elif self.device_state.phase == DevicePhase.FAULTED:
                self.device_state.phase = DevicePhase.BOOTED
            return ActorResult(status=status, body={"connector_id": connector_id, "status": status})
        if action == "authorize":
            id_tag = str(params["id_tag"])
            accepted = await cp.send_authorize(id_tag)
            self.device_state.authorize(id_tag, accepted)
            return ActorResult(status="Accepted" if accepted else "Rejected", body={"accepted": accepted})
        if action == "start_transaction":
            connector_id = int(params.get("connector_id", 1))
            id_tag = str(params.get("id_tag") or self.device_state.authorized_id_tag or "")
            if self.device_state.phase != DevicePhase.AUTHORIZED or self.device_state.authorized_id_tag != id_tag:
                raise RuntimeError("StartTransaction terminated because Authorize was not accepted")
            transaction_id = await cp.send_start_transaction(id_tag, connector_id)
            self.device_state.start(connector_id, transaction_id, id_tag)
            return ActorResult(status="Accepted", body={"transaction_id": transaction_id, "connector_id": connector_id})
        if action == "meter_values":
            connector_id = int(params.get("connector_id", 1))
            response = await cp.send_meter_values(connector_id, advance=bool(params.get("advance", True)))
            connector = cp.state.connectors[connector_id]
            return ActorResult(
                status="Accepted",
                body={"meter_wh": connector.meter.meter_wh, "transaction_id": connector.transaction_id},
                response=_response_body(response),
            )
        if action == "stop_transaction":
            connector_id = int(params.get("connector_id", 1))
            transaction_id = self.device_state.transactions.get(connector_id)
            if transaction_id is None:
                raise RuntimeError("StopTransaction requires an active transaction")
            sent = await cp.send_stop_transaction(connector_id, reason=str(params.get("reason", "Local")))
            if not sent:
                raise RuntimeError("StopTransaction was not sent")
            self.device_state.stop(connector_id)
            return ActorResult(status="Accepted", body={"transaction_id": transaction_id})
        if action == "heartbeat":
            response = await cp.send_heartbeat()
            return ActorResult(status="Accepted", body=_response_body(response))
        if action == "received_commands":
            requested_action = params.get("ocpp_action") or params.get("action")
            items = [
                dict(item)
                for item in cp.received_commands
                if requested_action is None or item.get("action") == requested_action
            ]
            return ActorResult(
                status="ok",
                body={"count": len(items), "items": items, "latest": items[-1] if items else None},
            )
        if action == "send_raw":
            frame = params.get("frame")
            if frame is None:
                frame = build_call(str(params["ocpp_action"]), dict(params.get("payload") or {}), params.get("unique_id"))
            return await self.send_frame(frame)
        if action == "duplicate":
            unique_id = str(params.get("unique_id") or f"{self.run_id}-duplicate")
            frames = duplicate_frames(str(params["ocpp_action"]), dict(params.get("payload") or {}), unique_id)
            first = await self.send_frame(frames[0])
            await self.send_frame(frames[1])
            first.body["copies"] = 2
            return first
        if action == "meter_before_start":
            return await self.send_frame(
                meter_before_start_frame(int(params.get("connector_id", 1)), params.get("unique_id"))
            )
        if action == "stop_before_start":
            return await self.send_frame(stop_before_start_frame(params.get("unique_id")))
        raise ValueError(f"Unsupported charger action: {action}")

    async def close(self) -> None:
        if self.ws is not None:
            await self.disconnect()
