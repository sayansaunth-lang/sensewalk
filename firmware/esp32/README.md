# SENSEWALK ESP32-S3 Firmware

FreeRTOS firmware for the real-time safety layer: ground/obstacle sensing (VL53L1X + HC-SR04), fall pre-check (MPU-6050), grip sensing, solenoid brake control, haptic feedback, and the UART link to the Raspberry Pi. See [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) for how this fits into the whole system and [`comms/PROTOCOL.md`](../../comms/PROTOCOL.md) for the wire format.

## Layout

```
include/config.h       Pin assignments + tunable thresholds (single source of truth)
src/sensors/           ToF pair, ultrasonic trio, IMU, grip — hardware drivers
src/actuators/         Solenoid brake, vibration motors
src/safety/            hazard_rules.h (pure logic, host-testable) + override.h (the hard safety layer)
src/comms/             uart_protocol.h (pure codec, host-testable) + uart_link.h (Serial2 I/O)
src/tasks.cpp          FreeRTOS task creation + priorities
src/globals.{h,cpp}    Shared hardware object instances
src/main.cpp           setup()/loop()
test/                  Host-native unit tests (Unity) for the pure-logic modules
```

## Building & flashing (PlatformIO)

```bash
# Install PlatformIO Core (one-time): https://platformio.org/install/cli
pip install platformio

cd firmware/esp32
pio run                       # build
pio run -t upload             # flash over USB
pio device monitor -b 115200  # serial log output
```

## Running the unit tests

The pure-logic modules (`safety/hazard_rules.h`, `comms/uart_protocol.h`) have no Arduino/hardware dependency and are unit tested on the host machine — no ESP32 or sensors required:

```bash
cd firmware/esp32
pio test -e native
```

These tests (and their Python-side equivalents in `comms/python/tests/`) must stay in sync — the wire format and checksum algorithm are defined once in `comms/PROTOCOL.md` and implemented twice.

## Wiring

Pin assignments live in `include/config.h`, not here — that's the single source of truth. Cross-check every pin against the actual component's datasheet before wiring (S3 in the learning roadmap) rather than trusting this comment.

## What's NOT yet done

This firmware is a complete, structured starting point, not a bench-calibrated final build. Before Phase 2 hardware bring-up:

- Every `TODO(calibrate)` threshold in `config.h` needs real bench data (B2/D2 in the learning roadmap) — the defaults are placeholders, not measurements.
- `sensors/tof.h` assumes both VL53L1X breakouts expose an XSHUT pin — confirm against the exact breakout purchased.
- The MOSFET/transistor driver stages (`actuators/brake.h`, `actuators/haptics.h`) assume active-HIGH GPIO switching logic-level compatible with the IRF520/2N2222 modules in the BOM — verify against those modules' actual gate/base wiring before first power-on (A3 in the learning roadmap).
