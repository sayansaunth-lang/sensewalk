# System Architecture

_Owned by C4 (E3) — keep this current from week 1, not written retroactively._

## Overview

Dual-core split: safety-critical sensing/actuation on the ESP32-S3 (deterministic, <50ms), everything compute-heavy on the Raspberry Pi 4 (vision, OCR, speech, connectivity). The ESP32 never depends on the Pi being alive — it has its own hard safety override.

```
                       ┌─────────────────────────────┐
                       │        Raspberry Pi 4        │
                       │                               │
   Pi Camera v3 ─────► │  OpenCV → MobileNet-SSD       │
                       │  Tesseract OCR (sign reading) │
                       │  Sensor-fusion state machine  │
                       │  Offline TTS (pyttsx3/eSpeak) │
   NEO-6M GPS ───────► │  SIM800L GSM (fall alert)     │
                       └──────────────┬────────────────┘
                                      │ UART (comms/ protocol)
                       ┌──────────────┴────────────────┐
                       │         ESP32-S3 (FreeRTOS)    │
                       │                                 │
  VL53L1X ToF (x2) ──► │  Ground/obstacle sensing task   │
  HC-SR04 (x3)     ──► │  Hazard threshold + debounce    │
  MPU-6050         ──► │  Orientation / fall pre-check   │
  Piezo grip (x2)  ──► │  Grip-presence gate             │
                       │  Hard safety override           │
                       │      │                          │
                       │      ▼                          │
                       │  MOSFET driver → 12V solenoids   │
                       │  Transistor driver → vibration   │
                       └─────────────────────────────────┘
```

## Design rules

1. **The ESP32 safety layer is independent.** If any sensor crosses a hard hazard threshold, the brake engages directly in firmware — it does not wait for a UART message from the Pi.
2. **Depth/distance and classification are separate concerns.** ToF/ultrasonic own distance; MobileNet-SSD only classifies (person/obstacle/chair) — it is not used for depth.
3. **Priority order** (used by the Pi-side fusion state machine): hard ToF drop-off > ultrasonic proximity > vision "person nearby" > OCR sign read. Physical safety always outranks informational alerts.
4. **States**: `IDLE → WALKING → HAZARD_WARNING → BRAKE_ENGAGED → FALL_ALERT` (and back). Sketch changes here before changing `fusion/` code.

## UART protocol

Spec lives in [`comms/PROTOCOL.md`](../comms/PROTOCOL.md), implemented on both sides ([`comms/python/`](../comms/python/), [`firmware/esp32/src/comms/`](../firmware/esp32/src/comms/)) with unit tests on each.

## Code map

| Concern | Lives in |
|---|---|
| Hard safety override, sensor drivers, actuator drivers | `firmware/esp32/src/{safety,sensors,actuators}/` |
| FreeRTOS task priorities | `firmware/esp32/src/tasks.cpp` |
| UART wire codec (both languages) | `comms/PROTOCOL.md`, `comms/python/protocol.py`, `firmware/esp32/src/comms/uart_protocol.h` |
| Fusion state machine | `fusion/state_machine.py` |
| Vision (camera/detection/OCR) | `vision/pi/src/` |
| Speech + buzzer fallback | `speech/` |
| Test tooling & logged results | `test/` |

## Open questions / decisions log

_Track decisions here as they're made (e.g., final message format, chosen fall-detection thresholds, camera mount angle) so the reasoning isn't lost by Phase 5._

- [x] UART message format finalized — comma-separated (Option A), see `comms/PROTOCOL.md` for the rationale
- [ ] Fall-detection thresholds set from real controlled-drop data (currently `TODO(calibrate)` placeholders in `firmware/esp32/include/config.h`)
- [ ] Ground-dropoff / obstacle-proximity thresholds set from real bench data (same file)
- [ ] Camera mount height/angle decided (M1 + C2)
