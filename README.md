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
3. Firmware setup: Arduino IDE or PlatformIO targeting ESP32-S3, add libraries as you need them to `firmware/esp32/lib/`.
4. Pi setup: Raspberry Pi OS (64-bit), Python 3.10+, work inside a venv — don't install packages into system Python.
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install opencv-python pytesseract pyttsx3 pyserial
   ```
5. Log every bench test (sensor calibration, braking trials, OCR success rate) into `test/` as you go — the final report needs real measured numbers, not estimates.

## Status

Phase 1 (procurement + sensor bench calibration) — not yet started.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system diagram and [docs/BOM.md](docs/BOM.md) for the full bill of materials and budget.
