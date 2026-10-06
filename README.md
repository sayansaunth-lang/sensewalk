# SENSEWALK

[![CI](https://github.com/sayansaunth-lang/sensewalk/actions/workflows/ci.yml/badge.svg)](https://github.com/sayansaunth-lang/sensewalk/actions/workflows/ci.yml)

Ultra-low-cost smart assistive mobility walker for visually impaired users. Dual-core architecture: an **ESP32-S3** handles real-time hazard sensing and active braking (FreeRTOS, <50ms response), a Raspberry Pi handles computer vision, OCR, speech, and GPS/GSM alerts. The team is building with a **Raspberry Pi 3B (1GB)** + Pi Camera Module 3 instead of the Pi 4 the original research report specced — see [docs/PI3B_LOW_RAM_SETUP.md](docs/PI3B_LOW_RAM_SETUP.md) for what that changes.

Academic project, 2nd Year B.Tech, 6-member team, 8-week build (5 phases). Target budget ₹15,000–17,000.

## Repo layout

```
firmware/esp32/    ESP32-S3 firmware (FreeRTOS): sensor polling, brake trigger, haptics, UART link
vision/pi/          Raspberry Pi: OpenCV pipeline, object detection (COCO + our own pothole model), Tesseract OCR
emergency/          Fall -> SMS with GPS location: NEO-6M parser, SIM800L driver, cancel-by-grip countdown
training/           Train/evaluate/export the custom ground-hazard (pothole) detector that runs on the Pi
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
3. **Firmware** (targeting ESP32-S3) — two ways to build it, same logic either way:
   - **PlatformIO** (canonical, CI-tested) — see [firmware/esp32/README.md](firmware/esp32/README.md):
     ```bash
     pip install platformio
     cd firmware/esp32
     pio run                # build
     pio test -e native     # run the host-native unit tests (no hardware needed)
     ```
   - **Arduino IDE** (flattened mirror, for whoever prefers the GUI) — see [firmware/esp32_arduino_ide/README.md](firmware/esp32_arduino_ide/README.md) for board package + library setup. Flash `SENSEWALK_blink_test/` first to confirm your toolchain works, then `SENSEWALK_ESP32/` for the real firmware.
4. **Python side** (Pi vision pipeline, comms, fusion, speech) — work inside a venv, don't install into system Python:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
   python -m pytest        # run the full test suite (comms, fusion, speech, vision logic)
   ```
   On the Pi itself, also install `vision/pi/requirements.txt` and run `vision/pi/models/download_models.sh` once to fetch the MobileNet-SSD weights (gitignored — not committed). **On a Pi 3B (1GB) specifically, read [docs/PI3B_LOW_RAM_SETUP.md](docs/PI3B_LOW_RAM_SETUP.md) first** — OS choice, swap, and two `main.py` flags (`--detector-backend tflite`, `--process-every-n-frames`) make the difference between usable and unusable on that hardware.
5. **Before the ESP32 exists or is wired up yet**, develop/demo the Pi side against a scripted synthetic sensor feed instead of real UART: `python3 vision/pi/src/main.py --camera opencv --camera-source 0 --sim --preview` (see [comms/python/sim_feed.py](comms/python/sim_feed.py)).
6. **Real bench calibration** (once the ESP32 + sensors are wired up): [test/bench_logger.py](test/bench_logger.py) gives a live dashboard and writes a ground-truth-labeled CSV while you walk test scenarios, ready for [test/analyze_detection_log.py](test/analyze_detection_log.py).
7. **Deploying to the Pi for real field tests**: copy [`vision/pi/sensewalk.service`](vision/pi/sensewalk.service) to `/etc/systemd/system/`, adjust the paths for your checkout location, then `sudo systemctl enable --now sensewalk`.
8. Log every bench test (sensor calibration, braking trials, OCR success rate) into `test/` as you go — see [test/README.md](test/README.md) and [test/FIELD_TEST_PLAN.md](test/FIELD_TEST_PLAN.md). The final report needs real measured numbers, not estimates.

## What's implemented

- **`comms/`** — UART wire protocol (comma-separated, checksummed) fully specified in [PROTOCOL.md](comms/PROTOCOL.md), with parity implementations and unit tests on both sides: [`comms/python/`](comms/python/) (Pi) and [`firmware/esp32/src/comms/`](firmware/esp32/src/comms/) (ESP32).
- **`fusion/`** — the sensor-fusion state machine ([`state_machine.py`](fusion/state_machine.py)) implementing the priority rules and 5-state cycle from ARCHITECTURE.md, unit tested against combined-hazard scenarios.
- **`emergency/`** — the fall-to-SMS chain: NMEA/GPS parsing that only trusts a valid, recent fix, a SIM800L AT-command driver, and a policy layer (cancel-by-grip countdown, no repeat spam, a failed send never suppresses a retry). Built so numbers come from the environment, never source code. Tested against a scripted fake modem; **not yet run on real hardware** — use `python -m emergency.send_test_sms` first. Wiring notes (USB-serial adapters, 2G, power) are in [docs/WIRING.md](docs/WIRING.md).
- **`training/`** — the project's own AI model: dataset cleaning/merging with leakage-safe splits (`prepare_dataset.py`), YOLOv8n fine-tuning + ONNX export (`train_hazard_model.py`), and an evaluator that scores the *deployed* OpenCV-DNN code path rather than just the training framework (`evaluate_onnx.py`). See [training/README.md](training/README.md) for the honest numbers and limits.
- **`vision/pi/`** — camera abstraction (Pi Camera Module 3 via picamera2, or a webcam/video file/network stream for dev-machine testing), a quantized TFLite MobileNet-SSD for people/objects (the default and tested end-to-end against real weights), an optional OpenCV-DNN Caffe backend (needs weights you supply), the project's own trained pothole detector (`--hazard-model`), "is this person actually close" logic from bounding-box size, a k-of-n confirmation filter against single-frame flicker,, OCR with a sign-detection trigger condition, a frame-skip flag (`--process-every-n-frames`) for slower boards, and a `main.py` wiring it all together with UART + speech.
- **`speech/`** — fixed alert-phrase vocabulary, offline TTS wrapper with latency logging, and a watchdog-thread piezo buzzer fallback that fires independently of TTS state.
- **`firmware/esp32/`** — FreeRTOS task structure (prioritised safety/ultrasonic/IMU/comms tasks), the hard sub-50ms safety override, and drivers for every sensor/actuator in the BOM. Pure-logic modules (hazard thresholds, UART codec) are unit tested on the host via PlatformIO's native test environment. See its own [README](firmware/esp32/README.md) for what's stubbed vs. calibrated.
- **`firmware/esp32_arduino_ide/`** — the same firmware, flattened into an Arduino-IDE-compatible sketch (no subfolders) for teammates who prefer the Arduino IDE over PlatformIO. Includes a standalone blink/serial sanity-check sketch to verify the toolchain before flashing the full firmware.
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
