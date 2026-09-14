"""Simulated ESP32 telemetry feed — lets the Pi-side stack (vision, fusion,
speech) be developed, tested, and demoed before the ESP32/sensors physically
exist or before the two boards are wired together.

Rather than emulating a virtual serial port (platform-specific, needs
socat/com0com), this generates the same SensorSnapshot values that
serial_link.py would have populated from real UART messages, so
vision/pi/src/main.py can run its full loop — fusion, speech, haptics
logging — against synthetic-but-realistic data with `--sim`.

Scenarios are deliberately simple, hand-authored sequences (not random
noise) so a demo is repeatable and a teammate can reason about what should
happen at each second, rather than debugging a flaky RNG.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from fusion.state_machine import SensorSnapshot


@dataclass
class SimEvent:
    """One point in a scripted scenario: at t=at_s seconds, apply `apply` to
    the running snapshot. Events are cumulative — later events build on
    earlier ones unless they explicitly reset a field."""

    at_s: float
    apply: Callable[[SensorSnapshot], None]
    label: str = ""


def _nominal_walking(s: SensorSnapshot) -> None:
    s.tof_gnd_mm = 300
    s.tof_gnd_baseline_mm = 300
    s.tof_fwd_mm = 2000
    s.us_l_cm = s.us_c_cm = s.us_r_cm = 150
    s.grip_left = s.grip_right = True
    s.last_grip_at = time.monotonic()
    s.fall_flag = False
    s.vision_person_nearby = False
    s.ocr_text = None


def _ground_dropoff(s: SensorSnapshot) -> None:
    s.tof_gnd_mm = 500  # +200mm over a 300mm baseline -> exceeds 150mm threshold


def _obstacle_close(s: SensorSnapshot) -> None:
    s.us_c_cm = 25


def _clear_hazard(s: SensorSnapshot) -> None:
    s.tof_gnd_mm = s.tof_gnd_baseline_mm
    s.us_l_cm = s.us_c_cm = s.us_r_cm = 150


def _person_detected(s: SensorSnapshot) -> None:
    s.vision_person_nearby = True


def _person_gone(s: SensorSnapshot) -> None:
    s.vision_person_nearby = False


def _sign_seen(s: SensorSnapshot) -> None:
    s.ocr_text = "ROOM 204"


def _grip_released(s: SensorSnapshot) -> None:
    s.grip_left = s.grip_right = False
    s.last_grip_at = time.monotonic() - 5  # already past GRIP_RELEASE_TIMEOUT_S


def _fall(s: SensorSnapshot) -> None:
    s.fall_flag = True


# A ~12s scripted walk exercising every state in the fusion state machine:
# WALKING -> BRAKE_ENGAGED (drop-off) -> WALKING -> HAZARD_WARNING (person)
# -> WALKING (sign) -> BRAKE_ENGAGED (obstacle) -> IDLE (hands off) -> FALL_ALERT.
DEFAULT_SCENARIO: list[SimEvent] = [
    SimEvent(0.0, _nominal_walking, "nominal walking"),
    SimEvent(2.0, _ground_dropoff, "pothole ahead"),
    SimEvent(4.0, _clear_hazard, "hazard cleared, grip still held -> release"),
    SimEvent(5.0, _person_detected, "person detected ahead"),
    SimEvent(6.5, _person_gone, "person moved out of frame"),
    SimEvent(7.0, _sign_seen, "OCR reads a room sign"),
    SimEvent(8.5, _obstacle_close, "ultrasonic: obstacle close"),
    SimEvent(9.5, _clear_hazard, "obstacle cleared"),
    SimEvent(9.6, _grip_released, "user lets go of both grips"),
    SimEvent(11.0, _fall, "fall detected"),
]


class SimulatedFeed:
    """Drop-in replacement for the real UART-fed SensorSnapshot in
    vision/pi/src/main.py's loop: call tick() once per frame and read
    .snapshot for the current values."""

    def __init__(self, scenario: Optional[list[SimEvent]] = None, loop: bool = True) -> None:
        self.scenario = scenario if scenario is not None else DEFAULT_SCENARIO
        self.loop = loop
        self.snapshot = SensorSnapshot()
        self._start = time.monotonic()
        self._applied_index = -1
        self._duration = max(e.at_s for e in self.scenario) if self.scenario else 0.0

    def tick(self) -> SensorSnapshot:
        elapsed = time.monotonic() - self._start
        if self.loop and self._duration > 0 and elapsed > self._duration:
            self._start = time.monotonic()
            self._applied_index = -1
            elapsed = 0.0

        for i, event in enumerate(self.scenario):
            if i > self._applied_index and elapsed >= event.at_s:
                event.apply(self.snapshot)
                self._applied_index = i
                if event.label:
                    print(f"[sim @ {elapsed:5.1f}s] {event.label}")

        return self.snapshot
