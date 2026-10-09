# File Guide

Every file tracked in this repository and what it does, generated from the repository's actual file list (`git ls-files`) and, for Python and C++ files, from the real classes and functions in the code. Regenerate it after adding files so it stays true.

**129 files.** Most were written for this project in the build-out sessions; the original scaffold (README, TEAM, BOM, ARCHITECTURE, folder layout) came first, and `comms/python/sim_feed.py`, `test/bench_logger.py`, `docs/WIRING.md`, `docs/DATASHEET_GOTCHAS.md` and `vision/pi/sensewalk.service` came from a separate working session. Files named `test_*.py` or in `tests/` are automated tests.

**Legend.** *Key functions* are the public classes/functions you would call or edit. Test files are listed by purpose only.

## Top level

| File | What it does | Key functions |
|---|---|---|
| `.gitattributes` | Forces Unix line endings on shell scripts and the systemd unit, so they do not break on the Pi when edited on Windows. |  |
| `.github/workflows/ci.yml` | GitHub Actions. On every push runs 4 jobs: Python tests, PlatformIO ESP32-S3 firmware build, Arduino IDE sketch build (latest ESP32 core), firmware C++ unit tests. |  |
| `.gitignore` | Keeps out virtual environments, build output, model weights downloaded by script, training runs and secrets. One deliberate exception: the trained pothole model is committed. |  |
| `README.md` | Project entry page: what SENSEWALK is, repo layout, team roles, how to build/test each part, what is implemented and what is not, CI badge. |  |
| `conftest.py` | Puts the repo root on Python's import path so every test can import `fusion`, `speech`, `comms`, `emergency`, `vision`. |  |
| `pytest.ini` | Tells pytest which folders hold tests, so `python -m pytest` runs the whole suite. |  |
| `requirements-dev.txt` | Python packages needed to run the full test suite on a laptop or in CI. |  |

## `comms/` - ESP32 to Pi link

| File | What it does | Key functions |
|---|---|---|
| `comms/PROTOCOL.md` | The ESP32 to Raspberry Pi UART spec: wiring, message format (`tag,value,seq,checksum`), every message tag, field-length limits, error-handling rules, and the 1000-message validation test. |  |
| `comms/python/__init__.py` | Package marker. |  |
| `comms/python/heartbeat_test.py` | Roadmap D1 check. Listens on the serial port for N heartbeat messages, counts gaps/corruption, writes a CSV, prints PASS/FAIL. | `main()` |
| `comms/python/protocol.py` | Pi-side codec for the UART protocol: build and parse lines, XOR checksum, reassemble lines from partial reads, track dropped messages, enforce the field-length limits. | `class ChecksumError`<br>`class MalformedLineError`<br>`class Message (fields, int_value)`<br>`compute_checksum()`<br>`encode()`<br>`decode()`<br>`class LineAssembler (feed)`<br>`class SequenceTracker (observe)` |
| `comms/python/serial_link.py` | Pi-side serial connection to the ESP32 (pyserial). Dispatches decoded messages to handlers, counts bad/dropped lines, and tracks whether the ESP32's heartbeat is still arriving. | `class LinkStats (mcu_alive)`<br>`class SerialLink (on_message, open, close, send, poll, feed)` |
| `comms/python/sim_feed.py` | Scripted fake ESP32 telemetry so the whole Pi side can run and be demoed before any hardware exists (`main.py --sim`). Repeatable scenarios, not random noise. | `class SimEvent`<br>`class SimulatedFeed (tick)` |
| `comms/python/tests/__init__.py` | Package marker. |  |
| `comms/python/tests/test_protocol.py` | Tests the codec: round trip, checksum example, bad/short/long lines, partial reads, gap and wrap-around tracking, length limits. |  |
| `comms/python/tests/test_serial_link.py` | Tests message dispatch, checksum-drop counting and heartbeat liveness without any serial port. |  |
| `comms/python/tests/test_sim_feed.py` | Tests that the scripted scenarios produce the expected sensor values over time. |  |

## `fusion/` - the decision state machine

| File | What it does | Key functions |
|---|---|---|
| `fusion/__init__.py` | Package marker. |  |
| `fusion/state_machine.py` | The decision brain on the Pi: five states, a fixed priority order (drop-off > obstacle > visual pothole > person > sign), grip-gated brake release, fall override. | `class State`<br>`class HazardKind`<br>`class SensorSnapshot`<br>`class Decision`<br>`class SensorFusion (update, history)` |
| `fusion/tests/__init__.py` | Package marker. |  |
| `fusion/tests/test_state_machine.py` | Tests priorities, combined hazards, brake hold/release, idle timeout, fall override, and that a visual pothole warns but never brakes. |  |

## `vision/pi/` - cameras, detection, OCR, the main Pi program

| File | What it does | Key functions |
|---|---|---|
| `vision/pi/models/.gitkeep` | Placeholder keeping the models folder. |  |
| `vision/pi/models/download_models.sh` | Intentionally refuses to run: the Caffe backend has no verified weight source. Points to the TFLite script. |  |
| `vision/pi/models/download_tflite_model.sh` | Downloads the people/object model (TFLite) and checks its SHA-256 before use. |  |
| `vision/pi/models/hazard_classes.txt` | Class names of the trained model (`pothole`). |  |
| `vision/pi/models/hazard_yolov8n_320.onnx` | The project's own trained pothole detector (11.6 MB). |  |
| `vision/pi/requirements.txt` | Packages needed on the Pi, with notes on tflite-runtime and picamera2. |  |
| `vision/pi/sensewalk.service` | systemd unit to start the pipeline at boot on the Pi. Edit its ExecStart line to add flags such as --hazard-model and --gsm-port. |  |
| `vision/pi/src/__init__.py` | Package marker. |  |
| `vision/pi/src/benchmark.py` | Run on the Pi to measure real speed of each model with no screen or camera: mean/median/p95 ms, FPS, CPU temperature, heat/power throttling, and a suggested --process-every-n-frames value. | `percentile()`<br>`time_calls()`<br>`suggest_every_n()`<br>`read_cpu_temp_c()`<br>`parse_throttled()`<br>`read_throttled()`<br>`make_frame()`<br>`main()` |
| `vision/pi/src/camera.py` | Camera sources: Pi Camera Module 3 (picamera2) or any webcam / video file / network stream (OpenCV), plus an FPS counter. | `class FrameSource (frames, close)`<br>`class Picamera2Source (frames, close)`<br>`class OpenCVCameraSource (frames, close)`<br>`class FPSCounter (tick)` |
| `vision/pi/src/detector.py` | All detection code: TFLite people/object detector, optional OpenCV-DNN Caffe detector, our YOLO pothole detector, the size-based 'person nearby' test, ground-hazard finder, and the 2-of-3 confirmation filter. | `class Detection (is_hazard_relevant)`<br>`class MobileNetSSDDetector (detect, draw_detections)`<br>`letterbox()`<br>`postprocess_yolo_output()`<br>`load_class_names()`<br>`class YoloOnnxDetector (detect)`<br>`is_nearby()`<br>`nearest_person()`<br>+6 more |
| `vision/pi/src/main.py` | The Pi program. Camera to detectors to fusion to speech/haptics/SMS, with flags for backend, frame skipping, hazard model, simulated sensors, GPS/GSM. | `build_camera()`<br>`build_detector()`<br>`main()` |
| `vision/pi/src/ocr.py` | Sign reading with Tesseract: find sign-like regions, clean the image, read text with a confidence score; reports a missing Tesseract clearly. | `class OcrResult`<br>`preprocess_for_ocr()`<br>`find_sign_like_regions()`<br>`should_attempt_ocr()`<br>`read_sign()` |
| `vision/pi/tests/__init__.py` | Package marker. |  |
| `vision/pi/tests/test_benchmark.py` | Tests the timing statistics, the frame-skip suggestion and the throttling-flag parser. |  |
| `vision/pi/tests/test_camera.py` | Tests the FPS counter. |  |
| `vision/pi/tests/test_detector.py` | Tests detection helpers and the TFLite output parsing and label loading. |  |
| `vision/pi/tests/test_hazard_detector.py` | Tests the YOLO decoder (letterbox, box mapping, NMS), nearby-person logic, ground-hazard picking and the confirmation filter. |  |
| `vision/pi/tests/test_hazard_model_smoke.py` | Loads the real committed pothole model and checks it runs on blank and oddly-shaped frames. |  |
| `vision/pi/tests/test_ocr.py` | Tests sign-region finding, preprocessing, and the missing-Tesseract error. |  |

## `training/` - the pothole model

| File | What it does | Key functions |
|---|---|---|
| `training/README.md` | How the pothole model was trained, its honest accuracy, limits, licences, and exact commands to reproduce or improve it. |  |
| `training/evaluate_onnx.py` | Scores the deployed model path (ONNX + OpenCV + our decoder) against labelled images: precision, recall, AP50. | `iou()`<br>`match_image()`<br>`precision_recall_at()`<br>`average_precision()`<br>`read_gt()`<br>`main()` |
| `training/prepare_dataset.py` | Cleans and merges pothole datasets: drops junk label lines and duplicates, and keeps near-duplicate images in the same split so test scores are honest. | `class Sample`<br>`class PrepReport`<br>`parse_label_file()`<br>`dhash64()`<br>`hamming()`<br>`cluster_by_similarity()`<br>`split_clusters()`<br>`collect_source()`<br>+2 more |
| `training/requirements-train.txt` | Packages for training (use on a PC, not the Pi), with install notes. |  |
| `training/results/hazard_deployed_eval_test.json` | Saved result of evaluating the deployed model on the held-out test split. |  |
| `training/results/hazard_metrics.json` | Saved training-framework metrics for the shipped model. |  |
| `training/tests/test_evaluate_onnx.py` | Tests the scoring maths (IoU, matching, AP). |  |
| `training/tests/test_prepare_dataset.py` | Tests label cleaning, duplicate removal and the no-leakage guarantee. |  |
| `training/train_hazard_model.py` | Fine-tunes YOLOv8n, evaluates on validation and test, exports ONNX plus the class list into vision/pi/models. `--evaluate-only` finishes an interrupted run. | `extract_metrics()`<br>`main()` |

## `speech/` - alerts

| File | What it does | Key functions |
|---|---|---|
| `speech/__init__.py` | Package marker. |  |
| `speech/buzzer_fallback.py` | Piezo buzzer watchdog on its own thread: if speech has not finished within a timeout it beeps anyway (more beeps = more severe). | `class BuzzerFallback (arm, disarm, buzz, close)` |
| `speech/phrases.py` | The fixed alert vocabulary with severity levels. Short fixed phrases keep speech fast and predictable. | `class Severity`<br>`class Phrase`<br>`render()`<br>`severity_of()` |
| `speech/tests/__init__.py` | Package marker. |  |
| `speech/tests/test_buzzer_fallback.py` | Tests the watchdog fires when speech stalls and stays silent when speech finishes. |  |
| `speech/tests/test_phrases.py` | Tests phrase rendering and that every key fusion uses exists. |  |
| `speech/tests/test_tts.py` | Tests speaking, repeat suppression, latency log, and the sign-reading regression. |  |
| `speech/tts.py` | Offline text-to-speech (pyttsx3): speaks phrases, suppresses rapid repeats, logs trigger-to-sound latency, degrades to a log line if no audio device. | `class LatencyRecord`<br>`class AlertSpeaker (available, speak, write_latency_log)` |

## `emergency/` - fall to SMS with GPS

| File | What it does | Key functions |
|---|---|---|
| `emergency/__init__.py` | Package marker. |  |
| `emergency/coordinator.py` | Glue the main loop calls each frame: runs the latch and countdown, sends the SMS off the main thread, and returns events (countdown / sent / failed) to speak. | `class EmergencyCoordinator (report_fall, fall_active, update, pop_events)` |
| `emergency/fall_confirm.py` | Two small state holders: a countdown the user cancels by gripping the handle, and a latch that holds the ESP32's one-shot fall report long enough to act on. | `class FallConfirmer (counting_down, seconds_left, observe)`<br>`class FallLatch (trigger, active)` |
| `emergency/nmea.py` | Reads the NEO-6M GPS: validates NMEA checksums, converts coordinates, accepts only a position the GPS marks valid, and remembers the latest fix with its age. | `class GpsFix`<br>`checksum_ok()`<br>`parse_coordinate()`<br>`parse_sentence()`<br>`class GpsReader (feed, fix_age_s, recent_fix, run)` |
| `emergency/notifier.py` | Decides what to send and when: map link only if the GPS fix is recent, retry after failure, suppress repeats after a success, numbers read from an environment variable. | `numbers_from_env()`<br>`class EmergencyResult (success)`<br>`class EmergencyNotifier (build_message, notify_fall)` |
| `emergency/send_test_sms.py` | Bench script: checks modem, network, GPS fix and sends one clearly-labelled TEST SMS, reporting which stage failed. Roadmap D3 deliverable. | `main()` |
| `emergency/sim800.py` | SIM800L GSM modem driver: checks the modem answers, network registration, signal strength, and sends a text-mode SMS. Validates the phone number and cleans the text first. | `class Sim800Error`<br>`sanitize_sms_text()`<br>`class Sim800 (command, ping, registered, signal_quality, send_sms)` |
| `emergency/tests/fakes.py` | Scripted fake SIM800L modem and a fast-forward clock used by the emergency tests. |  |
| `emergency/tests/test_coordinator.py` | Tests the full fall sequence: countdown, cancel by grip, one SMS only, failure reporting, latch outlasting the window. |  |
| `emergency/tests/test_fall_confirm.py` | Tests the countdown/cancel/re-arm behaviour. |  |
| `emergency/tests/test_nmea.py` | Tests checksums, coordinates, no-fix rejection, partial lines, stale fixes, using the standard NMEA example sentences. |  |
| `emergency/tests/test_notifier.py` | Tests message content, stale-fix handling, cooldown, retry after failure, per-number failures. |  |
| `emergency/tests/test_sim800.py` | Tests the exact AT-command byte sequence, number validation, timeouts and error handling. |  |

## `firmware/esp32/` - PlatformIO firmware (the tested original)

| File | What it does | Key functions |
|---|---|---|
| `firmware/esp32/README.md` | How to build, flash and test the PlatformIO firmware, folder layout, and what is still placeholder. |  |
| `firmware/esp32/include/config.h` | Single place for every pin assignment, timing value and hazard threshold. Values marked TODO(calibrate) are placeholders to replace with bench measurements. |  |
| `firmware/esp32/lib/.gitkeep` | Empty placeholder for local libraries. |  |
| `firmware/esp32/platformio.ini` | PlatformIO build settings: ESP32-S3 target, library dependencies, and the host-native test environment. |  |
| `firmware/esp32/src/actuators/brake.h` | Solenoid brake driver via the MOSFET modules: engage/release, plus a hard 5-second cutoff so a solenoid can never be left energised. | `class SolenoidBrake` |
| `firmware/esp32/src/actuators/haptics.h` | Left/right vibration-motor PWM driver (0-255 each). Works with both the old and new ESP32 PWM APIs. | `class Haptics` |
| `firmware/esp32/src/comms/uart_link.h` | Serial2 link to the Pi: non-blocking outgoing queue, incoming line parser, handles the Pi's haptic commands. Never blocks the safety task. | `class UartLink` |
| `firmware/esp32/src/comms/uart_protocol.h` | C++ side of the wire format: checksum, encode a line, decode a line, with the same field limits as the Python side. | `computeChecksum()`<br>`encodeLine()`<br>`decodeLine()` |
| `firmware/esp32/src/globals.cpp` | Creates the one shared instance of every sensor/actuator and starts them in order (I2C first). | `beginAll()` |
| `firmware/esp32/src/globals.h` | Declares those shared objects and `beginAll()`. | `beginAll()` |
| `firmware/esp32/src/main.cpp` | Entry point: starts everything, halts with a clear message if a ground/obstacle sensor is missing, then hands over to the FreeRTOS tasks. | `setup()`<br>`loop()` |
| `firmware/esp32/src/safety/hazard_rules.h` | Pure threshold logic: ground drop-off, forward obstacle, ultrasonic close, grip present, fall pattern, and the confirm-twice noise filter. No hardware, so it is unit tested on a PC. | `class ConfirmTwice`<br>`isValidToFReading()`<br>`isGroundDropoff()`<br>`isForwardObstacleClose()`<br>`isUltrasonicClose()`<br>`isGripPresent()`<br>`isFallDetected()` |
| `firmware/esp32/src/safety/override.h` | The hard safety layer: reads sensors and engages the brake by itself, independent of the Pi; grip gates release; logs its own decision time. | `class SafetyOverride` |
| `firmware/esp32/src/sensors/grip.h` | Reads the two piezo grip sensors and reports hand-present state. | `class GripPair` |
| `firmware/esp32/src/sensors/imu.h` | MPU-6050 driver with a complementary filter for pitch/roll and a rolling window of features for fall detection. | `class Imu` |
| `firmware/esp32/src/sensors/tof.h` | Two VL53L1X laser distance sensors (ground + forward): brings them up one at a time to give each its own I2C address, and tracks a slow ground baseline. | `class ToFPair` |
| `firmware/esp32/src/sensors/ultrasonic.h` | Three HC-SR04 sensors read one at a time (never together, to avoid cross-talk). | `class UltrasonicTrio` |
| `firmware/esp32/src/tasks.cpp` | The four FreeRTOS tasks: safety (highest priority), ultrasonic, IMU, comms (lowest). | `safetyTask()`<br>`ultrasonicTask()`<br>`imuTask()`<br>`commsTask()`<br>`startAll()` |
| `firmware/esp32/src/tasks.h` | Task priorities and stack size. | `startAll()` |
| `firmware/esp32/test/test_hazard_rules/test_main.cpp` | 10 C++ unit tests for the threshold logic (run on a PC by CI). |  |
| `firmware/esp32/test/test_uart_protocol/test_main.cpp` | 9 C++ unit tests for the wire format, including the checksum example that must match Python and the length-limit cases. |  |

## `firmware/esp32_arduino_ide/` - the same firmware for Arduino IDE

| File | What it does | Key functions |
|---|---|---|
| `firmware/esp32_arduino_ide/README.md` | Step-by-step Arduino IDE setup: board package, two libraries, board settings, blink test first, then the full firmware. |  |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/SENSEWALK_ESP32.ino` | Main sketch (setup/loop). Same as the PlatformIO main.cpp. | `setup()`<br>`loop()` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/actuators_brake.h` | Copy of actuators/brake.h (Arduino IDE needs a flat folder). | `class SolenoidBrake` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/actuators_haptics.h` | Copy of actuators/haptics.h. | `class Haptics` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/config.h` | Copy of include/config.h: all pins, timings and thresholds. Edit pins here to match your wiring. |  |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/globals.cpp` | Copy of globals.cpp. | `beginAll()` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/globals.h` | Copy of globals.h. | `beginAll()` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/hazard_rules.h` | Copy of safety/hazard_rules.h. | `class ConfirmTwice`<br>`isValidToFReading()`<br>`isGroundDropoff()`<br>`isForwardObstacleClose()`<br>`isUltrasonicClose()`<br>`isGripPresent()`<br>`isFallDetected()` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/safety_override.h` | Copy of safety/override.h. | `class SafetyOverride` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/sensors_grip.h` | Copy of sensors/grip.h. | `class GripPair` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/sensors_imu.h` | Copy of sensors/imu.h. | `class Imu` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/sensors_tof.h` | Copy of sensors/tof.h. | `class ToFPair` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/sensors_ultrasonic.h` | Copy of sensors/ultrasonic.h. | `class UltrasonicTrio` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/tasks.cpp` | Copy of tasks.cpp. | `safetyTask()`<br>`ultrasonicTask()`<br>`imuTask()`<br>`commsTask()`<br>`startAll()` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/tasks.h` | Copy of tasks.h. | `startAll()` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/uart_link.h` | Copy of comms/uart_link.h. | `class UartLink` |
| `firmware/esp32_arduino_ide/SENSEWALK_ESP32/uart_protocol.h` | Copy of comms/uart_protocol.h. | `computeChecksum()`<br>`encodeLine()`<br>`decodeLine()` |
| `firmware/esp32_arduino_ide/SENSEWALK_blink_test/SENSEWALK_blink_test.ino` | Tiny bring-up sketch: blinks an LED and prints over serial, to prove your IDE, board and port work before flashing the real firmware. | `setup()`<br>`loop()` |

## `test/` - bench logging and analysis

| File | What it does | Key functions |
|---|---|---|
| `test/FIELD_TEST_PLAN.md` | Written Phase 5 plan: braking distance, false-alert rate, battery life, plus demo rehearsal checklist. |  |
| `test/README.md` | What the test data folders hold and the CSV formats for each kind of log. |  |
| `test/analyze_detection_log.py` | Turns a labelled hazard-detection CSV into true/false positive and negative counts, rates and accuracy. | `class ConfusionCounts (total, false_positive_rate, false_negative_rate, accuracy, add, print_report)`<br>`parse_bool_field()`<br>`main()` |
| `test/bench_logger.py` | Live sensor dashboard that records a CSV with a ground-truth key you press during a test walk; feeds analyze_detection_log.py. | `class BenchLogger (run)`<br>`main()` |
| `test/data/.gitkeep` | Placeholder for recorded test clips (large video is git-ignored). |  |
| `test/logs/.gitkeep` | Placeholder for CSV logs from bench and field runs. |  |
| `test/test_analyze_detection_log.py` | Tests the analyser's counting and CSV handling. |  |
| `test/test_bench_logger.py` | Tests the bench logger's labelling and CSV output. |  |

## `scripts/` - setup helpers

| File | What it does | Key functions |
|---|---|---|
| `scripts/pi_setup.sh` | One command, run ON the Pi: installs system packages, clones the repo, builds the venv (with --system-site-packages), installs Python packages and the TFLite runtime, downloads and checksum-verifies the models, checks both models load, and checks the camera is detected. |  |

## `docs/`

| File | What it does | Key functions |
|---|---|---|
| `docs/ARCHITECTURE.md` | System design: the two-processor split, design rules (ESP32 brakes alone; vision only warns), fusion priority order, code map, decisions log. |  |
| `docs/BOM.md` | Bill of materials and budget, including the Pi 3B substitution and the two USB-to-serial adapters that were missing from the original report. |  |
| `docs/DATASHEET_GOTCHAS.md` | Pre-filled 'read this before wiring' sheet per component (voltage/current limits, traps). Its Raspberry Pi section covers the Pi 3B you actually have. |  |
| `docs/FILE_GUIDE.md` | This guide: every file in the repository and what it does. Generated from git ls-files and the real code, so it cannot silently drift. |  |
| `docs/PI3B_LOW_RAM_SETUP.md` | How to run the vision pipeline on a Pi 3B with 1 GB: OS choice, swap, installing dependencies (venv with --system-site-packages), the speed flags, the optional pothole model. |  |
| `docs/SENSEWALK_Project_Report.pdf` | The 12-page report: what was built, the AI models with real numbers, a phase-by-phase plan for your real walker, what was and was not verified. |  |
| `docs/TEAM.md` | Six team roles, what each owns, pairing rules and per-person checklists (from the learning roadmap). |  |
| `docs/WIRING.md` | ESP32-S3 pin map, power chain, component gotchas, and how to connect GPS and GSM to the Pi through USB-serial adapters (including SIM800L power and the 2G warning). |  |

## `cad/`

| File | What it does | Key functions |
|---|---|---|
| `cad/brackets/.gitkeep` | Empty placeholder so Git keeps the folder. Sensor bracket CAD files go here (M1). Nothing designed yet. |  |
| `cad/chassis/.gitkeep` | Empty placeholder for chassis CAD (M1). Nothing designed yet. |  |

## Not in the repository on purpose

- Downloaded models: `ssd_mobilenet_v1_coco_quant.tflite`, `coco_labelmap.txt` (run `vision/pi/models/download_tflite_model.sh`).
- The raw pothole datasets (licences; see `training/README.md`).
- Training runs and PyTorch checkpoints (`training/runs/`, `*.pt`), which are large and reproducible.
- Phone numbers: they are read from the `SENSEWALK_EMERGENCY_NUMBERS` environment variable, never stored.
