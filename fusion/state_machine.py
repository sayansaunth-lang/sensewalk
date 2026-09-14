"""SENSEWALK system state machine (D4 in the learning roadmap).

Runs on the Pi. Combines ToF/ultrasonic/IMU telemetry arriving over UART
(comms/python/serial_link.py) with vision detections (vision/pi) into one
coherent state, following the explicit priority order from
docs/ARCHITECTURE.md:

    hard ToF drop-off > ultrasonic proximity > vision "person nearby" > OCR sign read

The ESP32's own hard safety override (firmware/esp32/src/safety/) is an
independent, lower-level backstop — this state machine is for user-facing
alert selection and system-level bookkeeping, not for the safety-critical
brake decision itself.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class State(Enum):
    IDLE = auto()
    WALKING = auto()
    HAZARD_WARNING = auto()
    BRAKE_ENGAGED = auto()
    FALL_ALERT = auto()


class HazardKind(Enum):
    NONE = auto()
    GROUND_DROPOFF = auto()  # hard ToF drop-off — highest priority
    OBSTACLE_CLOSE = auto()  # ultrasonic proximity
    PERSON_NEARBY = auto()  # vision classification
    SIGN_READ = auto()  # OCR result — informational only, never a hazard escalation


# Priority order, highest first — matches docs/ARCHITECTURE.md exactly.
HAZARD_PRIORITY = [
    HazardKind.GROUND_DROPOFF,
    HazardKind.OBSTACLE_CLOSE,
    HazardKind.PERSON_NEARBY,
    HazardKind.SIGN_READ,
]

# Thresholds — starting points only. Section B2/D2 of the learning roadmap
# is explicit that these must be replaced with values derived from real
# bench/field data, not guessed. Keep the guessed defaults isolated here so
# that swap is a one-line change per threshold, not a code hunt.
GROUND_DROPOFF_MM = 150  # sudden increase beyond this vs. rolling baseline = drop-off
OBSTACLE_CLOSE_CM = 40
GRIP_RELEASE_TIMEOUT_S = 2.0  # both grips released this long -> treat as hands-off


@dataclass
class SensorSnapshot:
    """Latest known value for every input the fusion logic reads. Fields
    default to None so partial data (e.g. vision not running yet) degrades
    gracefully instead of crashing the state machine."""

    tof_fwd_mm: Optional[int] = None
    tof_gnd_mm: Optional[int] = None
    tof_gnd_baseline_mm: Optional[int] = None
    us_l_cm: Optional[int] = None
    us_c_cm: Optional[int] = None
    us_r_cm: Optional[int] = None
    grip_left: bool = False
    grip_right: bool = False
    fall_flag: bool = False
    vision_person_nearby: bool = False
    ocr_text: Optional[str] = None
    mcu_alive: bool = True
    last_grip_at: float = field(default_factory=time.monotonic)


@dataclass
class Decision:
    state: State
    hazard: HazardKind
    alert_phrase_key: Optional[str]  # key into speech/phrases.py vocabulary
    reason: str


class SensorFusion:
    """Call update(snapshot) on every new reading; read .state for the
    current state and .decide() for the latest full decision (state +
    which hazard drove it + which alert phrase to speak)."""

    def __init__(self) -> None:
        self.state = State.IDLE
        self._history: list[tuple[State, State, str]] = []

    def _classify_hazard(self, s: SensorSnapshot) -> HazardKind:
        if s.tof_gnd_mm is not None and s.tof_gnd_baseline_mm is not None:
            if s.tof_gnd_mm - s.tof_gnd_baseline_mm > GROUND_DROPOFF_MM:
                return HazardKind.GROUND_DROPOFF

        closest_us = [v for v in (s.us_l_cm, s.us_c_cm, s.us_r_cm) if v is not None]
        if closest_us and min(closest_us) < OBSTACLE_CLOSE_CM:
            return HazardKind.OBSTACLE_CLOSE

        if s.vision_person_nearby:
            return HazardKind.PERSON_NEARBY

        if s.ocr_text:
            return HazardKind.SIGN_READ

        return HazardKind.NONE

    def _transition(self, new_state: State, reason: str) -> None:
        if new_state != self.state:
            self._history.append((self.state, new_state, reason))
        self.state = new_state

    def update(self, s: SensorSnapshot) -> Decision:
        hazard = self._classify_hazard(s)

        if s.fall_flag:
            self._transition(State.FALL_ALERT, "fall_flag set")
            return Decision(self.state, hazard, "fall_alert", "MCU/IMU fall pre-check tripped")

        grip_engaged = s.grip_left or s.grip_right
        hands_off_duration = time.monotonic() - s.last_grip_at

        if hazard in (HazardKind.GROUND_DROPOFF, HazardKind.OBSTACLE_CLOSE):
            self._transition(State.BRAKE_ENGAGED, f"hazard={hazard.name}")
            phrase = "pothole_ahead" if hazard is HazardKind.GROUND_DROPOFF else "obstacle_close"
            return Decision(self.state, hazard, phrase, f"{hazard.name} within threshold")

        if self.state is State.BRAKE_ENGAGED:
            # Only release once the immediate hazard has cleared AND the
            # user has re-gripped — mirrors B3's "grip gates auto-release".
            if grip_engaged:
                self._transition(State.WALKING, "hazard cleared + grip re-engaged")
            else:
                return Decision(self.state, HazardKind.NONE, None, "hazard cleared, waiting for grip")

        if hazard is HazardKind.PERSON_NEARBY:
            self._transition(State.HAZARD_WARNING, "vision: person nearby")
            return Decision(self.state, hazard, "person_close", "vision detected a nearby person")

        if hazard is HazardKind.SIGN_READ:
            # Informational only — never escalates state past WALKING.
            if self.state in (State.IDLE, State.WALKING):
                self._transition(State.WALKING, "reading sign, no escalation")
            return Decision(self.state, hazard, "sign_read", f"OCR: {s.ocr_text}")

        if not grip_engaged and hands_off_duration > GRIP_RELEASE_TIMEOUT_S:
            self._transition(State.IDLE, "hands off grips")
            return Decision(self.state, HazardKind.NONE, None, "idle: no grip contact")

        self._transition(State.WALKING, "nominal")
        return Decision(self.state, HazardKind.NONE, None, "nominal walking")

    def history(self) -> list[tuple[State, State, str]]:
        return list(self._history)
