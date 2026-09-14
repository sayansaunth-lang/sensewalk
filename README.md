# SENSEWALK

Ultra-low-cost smart assistive mobility walker for visually impaired users. Dual-core architecture: an **ESP32-S3** handles real-time hazard sensing and active braking (FreeRTOS, <50ms response), a **Raspberry Pi 4** handles computer vision, OCR, speech, and GPS/GSM alerts.

Academic project, 2nd Year B.Tech, 6-member team, 8-week build (5 phases). Target budget ₹15,000–17,000.

## Repo layout

```
firmware/esp32/    ESP32-S3 firmware (FreeRTOS): sensor polling, brake trigger, haptics, UART link
vision/pi/          Raspberry Pi: OpenCV pipeline, MobileNet-SSD detection, Tesseract OCR
comms/               UART protocol spec + code shared by both boards (message format, parsing)
fusion/              Sensor-fusion / decision state machine (runs on the Pi)
speech/              Offline TTS (pyttsx3/eSpeak), alert phrase vocabulary, buzzer fallback
cad/                 Fusion 360 exports, chassis assemblies, 3D-printable bracket files
docs/                Architecture diagram, team roles, BOM, test plans, datasheet "gotcha sheets"
test/                Field test logs, bench calibration data, results spreadsheets
```

## Team roles

See [docs/TEAM.md](docs/TEAM.md) for full role assignments and personal checklists.

| Member | Role | Owns |
|---|---|---|
| M1 | Chassis & Ergonomics Lead | `cad/` |
| M2 | Actuation & Power Systems Lead | Power wiring, solenoid drivers |
| C1 | Embedded Firmware Lead | `firmware/esp32/` |
| C2 | Computer Vision & OCR Lead | `vision/pi/` |
| C3 | Systems Integration & Sensor-Fusion Lead | `comms/`, `fusion/` |
| C4 | Software, Speech & Test Lead | `speech/`, `test/`, this README |

## Branching convention

One branch per subsystem, merged into `main` only once that module's own test/output passes:

- `firmware` (C1, M2 on actuator wiring)
- `vision` (C2)
- `comms-fusion` (C3)
- `speech-test` (C4)
- `cad` (M1, M2)

Open a pull request into `main` for every merge — get at least one teammate's review first, even on a student project.

## Getting started

1. Clone the repo, pick your branch above.
2. Read your track in the learning roadmap (ask whoever holds the SENSEWALK Learning Roadmap PDF) before writing code — B1/B2 for firmware, C1v/C2v for vision, D1 for comms, E1/E2 for speech/test.
3. **Firmware** (PlatformIO, targeting ESP32-S3) — see [firmware/esp32/README.md](firmware/esp32/README.md):
   ```bash
   pip install platformio
   cd firmware/esp32
   pio run                # build
   pio test -e native     # run the host-native unit tests (no hardware needed)
   ```
4. **Python side** (Pi vision pipeline, comms, fusion, speech) — work inside a venv, don't install into system Python:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
   python -m pytest        # run the full test suite (comms, fusion, speech, vision logic)
   ```
   On the Pi itself, also install `vision/pi/requirements.txt` and run `vision/pi/models/download_models.sh` once to fetch the MobileNet-SSD weights (gitignored — not committed).
5. **Before the ESP32 exists or is wired up yet**, develop/demo the Pi side against a scripted synthetic sensor feed instead of real UART: `python3 vision/pi/src/main.py --camera opencv --camera-source 0 --sim --preview` (see [comms/python/sim_feed.py](comms/python/sim_feed.py)).
6. **Real bench calibration** (once the ESP32 + sensors are wired up): [test/bench_logger.py](test/bench_logger.py) gives a live dashboard and writes a ground-truth-labeled CSV while you walk test scenarios, ready for [test/analyze_detection_log.py](test/analyze_detection_log.py).
7. **Deploying to the Pi for real field tests**: copy [`vision/pi/sensewalk.service`](vision/pi/sensewalk.service) to `/etc/systemd/system/`, adjust the paths for your checkout location, then `sudo systemctl enable --now sensewalk`.
8. Log every bench test (sensor calibration, braking trials, OCR success rate) into `test/` as you go — see [test/README.md](test/README.md) and [test/FIELD_TEST_PLAN.md](test/FIELD_TEST_PLAN.md). The final report needs real measured numbers, not estimates.

## What's implemented

- **`comms/`** — UART wire protocol (comma-separated, checksummed) fully specified in [PROTOCOL.md](comms/PROTOCOL.md), with parity implementations and unit tests on both sides: [`comms/python/`](comms/python/) (Pi) and [`firmware/esp32/src/comms/`](firmware/esp32/src/comms/) (ESP32).
- **`fusion/`** — the sensor-fusion state machine ([`state_machine.py`](fusion/state_machine.py)) implementing the priority rules and 5-state cycle from ARCHITECTURE.md, unit tested against combined-hazard scenarios.
- **`vision/pi/`** — camera abstraction (Pi Camera v3 via picamera2, or a webcam/video file for dev-machine testing), MobileNet-SSD detection, OCR with a sign-detection trigger condition, and a `main.py` wiring it all together with UART + speech.
- **`speech/`** — fixed alert-phrase vocabulary, offline TTS wrapper with latency logging, and a watchdog-thread piezo buzzer fallback that fires independently of TTS state.
- **`firmware/esp32/`** — FreeRTOS task structure (prioritised safety/ultrasonic/IMU/comms tasks), the hard sub-50ms safety override, and drivers for every sensor/actuator in the BOM. Pure-logic modules (hazard thresholds, UART codec) are unit tested on the host via PlatformIO's native test environment. See its own [README](firmware/esp32/README.md) for what's stubbed vs. calibrated.
- **`comms/python/sim_feed.py`** — a scripted synthetic ESP32 telemetry feed so the whole Pi-side stack can be developed and demoed before the ESP32/sensors exist or are wired up (`vision/pi/src/main.py --sim`).
- **`test/bench_logger.py`** — live sensor dashboard + ground-truth-labeled CSV logger, turning the "log 50 test walks" deliverables into a tool the team actually runs, feeding straight into `test/analyze_detection_log.py`.
- **`docs/WIRING.md`** / **`docs/DATASHEET_GOTCHAS.md`** — concrete pin-to-component wiring reference and pre-filled per-component gotcha sheets (S3 in the learning roadmap), to verify against the actual purchased parts rather than starting from a blank page.
- **`vision/pi/sensewalk.service`** — systemd unit for running the pipeline automatically on Pi boot during real field tests.
- **CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) — runs the Python test suite, builds the firmware, and runs the firmware's native unit tests on every push/PR.

## What's NOT yet done (by design — this is a scaffold, not a calibrated build)

Every `TODO(calibrate)` threshold in [`firmware/esp32/include/config.h`](firmware/esp32/include/config.h) and the defaults in [`fusion/state_machine.py`](fusion/state_machine.py) are starting points, not measurements — Phase 1/2 bench calibration against real sensor data (B2/D2 in the learning roadmap) still has to happen and the numbers here have to be replaced, not trusted as-is. No MobileNet-SSD/OCR model weights are committed (see `vision/pi/models/download_models.sh`). Mechanical/CAD work (`cad/`) hasn't started.

## Status

Software scaffold for all five phases is in place; Phase 1 (procurement + sensor bench calibration against real hardware) has not started.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system diagram and [docs/BOM.md](docs/BOM.md) for the full bill of materials and budget.
