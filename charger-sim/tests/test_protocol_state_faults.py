from __future__ import annotations

import unittest

from faults import duplicate_frames, meter_before_start_frame, stop_before_start_frame
from protocol.ocpp16.frames import CALL, build_call, decode_frame, encode_frame
from protocol.ocpp16.state import DevicePhase, DeviceState


class FrameTests(unittest.TestCase):
    def test_standard_ocpp_array_round_trip(self) -> None:
        frame = build_call("Heartbeat", {}, unique_id="same-id")
        self.assertEqual(frame, [CALL, "same-id", "Heartbeat", {}])
        self.assertEqual(decode_frame(encode_frame(frame)), frame)

    def test_duplicate_preserves_same_unique_id_and_payload(self) -> None:
        frames = duplicate_frames("StatusNotification", {"status": "Available"}, "stable")
        self.assertEqual(frames[0], frames[1])
        self.assertEqual(frames[0][1], "stable")

    def test_out_of_order_faults_are_standard_calls(self) -> None:
        self.assertEqual(meter_before_start_frame()[0], CALL)
        self.assertEqual(meter_before_start_frame()[2], "MeterValues")
        self.assertEqual(stop_before_start_frame()[2], "StopTransaction")


class StateMachineTests(unittest.TestCase):
    def test_authorize_rejection_prevents_start(self) -> None:
        state = DeviceState()
        state.connect()
        state.boot(True)
        state.authorize("DENIED", False)
        with self.assertRaisesRegex(RuntimeError, "successful Authorize"):
            state.start(1, 100, "DENIED")

    def test_happy_state_machine(self) -> None:
        state = DeviceState()
        state.connect()
        state.boot(True)
        state.authorize("TAG", True)
        state.start(1, 100, "TAG")
        self.assertEqual(state.phase, DevicePhase.CHARGING)
        self.assertEqual(state.stop(1), 100)
        self.assertEqual(state.phase, DevicePhase.BOOTED)


if __name__ == "__main__":
    unittest.main()
