# Team Structure & Role Assignment

6 members (2 Mechanical, 4 CS/CE). Roles respect each member's branch while giving everyone hands-on exposure to both hardware and software. Ownership creates accountability; pairing prevents silos.

| Member | Branch | Role | Primary owns |
|---|---|---|---|
| M1 | Mechanical | Chassis & Ergonomics Lead | Frame/CAD, wheel & caster selection, handle-grip ergonomics, sensor mounting geometry, 3D-printed brackets, mechanical safety |
| M2 | Mechanical | Actuation & Power Systems Lead | Solenoid brake mechanism, MOSFET driver wiring, battery pack + buck converter + TP4056, fusing, wiring harness, enclosure |
| C1 | CS/CE | Embedded Firmware Lead (ESP32-S3) | FreeRTOS real-time code, VL53L1X ToF + HC-SR04 ultrasonic drivers, brake trigger logic, piezo grip sensing, vibration-motor haptics |
| C2 | CS/CE | Computer Vision & OCR Lead (Raspberry Pi) | Pi Camera v3 pipeline, OpenCV, MobileNet-SSD object detection, Tesseract OCR sign reading |
| C3 | CS/CE | Systems Integration & Sensor-Fusion Lead | Pi OS setup, ESP32<->Pi UART protocol, MPU-6050 fall detection, GPS/GSM emergency alert, decision-fusion logic |
| C4 | CS/CE | Software, Speech & Test Lead | Offline TTS + buzzer fallback, overall system state machine, logging/telemetry, test plan, documentation, demo video |

## Pairing rule

No one works in total isolation:
- **M2 + C1** pair during brake-trigger wiring (mechanical actuator + firmware signal meet exactly there).
- **M1 + C2** pair when deciding camera mounting height/angle (mechanical decision, vision consequence).
- **C3** pairs with everyone at integration time — owns the UART link between the two boards.

Rotate one "shadow session" per phase so every member touches at least one hardware task and one software task by project end.

## Personal checklists

### M1 — Chassis & Ergonomics Lead
- [ ] Complete Fusion 360 (or equivalent) basics tutorial path
- [ ] Read datasheets for VL53L1X, HC-SR04, Pi Camera v3 for exact physical dimensions/mount points
- [ ] Produce full CAD assembly with sensor and board mounts dimensioned
- [ ] Design and test the solenoid-to-wheel-lock mechanical linkage on the bench (paired with M2)
- [ ] 3D print and fit-check all sensor mounting brackets
- [ ] Participate in a Phase 5 field test, logging physical reliability observations

### M2 — Actuation & Power Systems Lead
- [ ] Refresh Ohm's law / basic circuit analysis
- [ ] Read IRF520, LM2596, TP4056 datasheets fully, including limits/warnings sections
- [ ] Build and multimeter-test the MOSFET solenoid driver stage on perfboard
- [ ] Build and test the transistor driver stage for the vibration motors
- [ ] Assemble the full power chain: battery -> TP4056 -> fuse -> buck converter -> loads, reviewed by a teammate before first power-on
- [ ] Own and document the in-line fuse sizing decision

### C1 — Embedded Firmware Lead
- [ ] Complete plain GPIO/ADC/PWM ESP32-S3 basics before touching FreeRTOS
- [ ] Complete a two-task FreeRTOS demo with different priorities
- [ ] Get VL53L1X and HC-SR04 reading reliably; log-validate the pothole/curb detection rule (50+ test walks)
- [ ] Wire and test solenoid brake + piezo grip + vibration motor firmware logic (paired with M2)
- [ ] Implement and time-measure the hard ESP32-side safety override (<50ms, independent of the Pi)
- [ ] Write your side of the UART protocol against the agreed spec

### C2 — Computer Vision & OCR Lead
- [ ] Get comfortable with Linux CLI and SSH into the Pi headlessly
- [ ] Get Pi Camera v3 streaming via libcamera; confirm no thermal throttling over a 10-minute test
- [ ] Complete OpenCV basics: colour conversion, thresholding, contours, live FPS counter
- [ ] Get a pretrained MobileNet-SSD model detecting 3+ object classes live, with measured FPS
- [ ] Get Tesseract OCR reading printed text reliably; add preprocessing for camera frames
- [ ] Document real failure modes of vision and OCR honestly (lighting, angle, distance)

### C3 — Systems Integration & Sensor-Fusion Lead
- [ ] Write the UART message-format spec; get sign-off from C1 and C2 before either side writes protocol code
- [ ] Build the minimal ESP32-to-Pi heartbeat test (1000 messages, near-zero loss)
- [ ] Get MPU-6050 orientation stable with a complementary filter; log-test a fall-detection rule
- [ ] Get GPS fix outdoors and one full SMS alert via SIM800L, powered from the main rail (not a logic pin)
- [ ] Sketch and implement the full system state machine with documented priority rules
- [ ] Lead the Phase 4 integration sessions

### C4 — Software, Speech & Test Lead
- [ ] Get offline TTS producing spoken alerts with measured trigger-to-sound latency
- [ ] Wire and test the speaker/amplifier or earpiece output, and the piezo buzzer fallback
- [ ] Design the fixed alert-phrase vocabulary with the team, prioritised by hazard severity
- [ ] Design the Phase 5 test plan (braking distance, false-positive rate, battery life) in writing before field trials
- [ ] Run and log 10+ trials per test type with honest mean/spread numbers
- [ ] Own and keep current the README and architecture diagram from week 1; lead final demo rehearsal

## Shared skills (non-negotiable for all 6 members)

- **Git & GitHub**: core loop (clone, branch, commit, push, PR); everyone makes at least one reviewed PR before Phase 1 ends.
- **Soldering & bench safety**: institution's lab safety induction first, then perfboard practice before soldering anything permanent.
- **Reading a datasheet properly**: one "gotcha sheet" per owned component (voltage/current limits, pinout, thermal/current-spike warnings), shared with the team before that part is wired in.
