# Datasheet Gotcha Sheets

S3 in the learning roadmap, non-negotiable: "Practice on one component per person before the project starts, and share a one-paragraph 'gotcha summary' with the team for each part you personally own." Almost every real bug in this class of project (SIM800L brownouts, I2C address clashes, solenoid duty-cycle overheating) is explicitly warned about in a datasheet nobody read past the first page.

The entries below are pre-filled with the gotchas already known from the research/roadmap so the team isn't starting from zero — **but every owner listed must verify these against the actual datasheet PDF for the exact part purchased** (voltage/current numbers vary between vendors and revisions) and add anything missed. Treat this file as a first draft, not a finished reference.

## VL53L1X (ToF sensor) — owner: C1

- No fixed alternate I2C address pin on most breakouts — address reassignment must happen via XSHUT at boot, one sensor at a time (see `firmware/esp32/src/sensors/tof.h`).
- `65535` (0xFFFF) is the library's "no target / out of range" sentinel — never treat it as a real distance reading.
- Timing budget vs. range/update-rate trade-off: a longer budget gives more accurate long-range readings but slower updates. 33ms was chosen as a starting point for a device polling ~50Hz elsewhere in the system — revisit if bench data shows it's too slow or too noisy.

## HC-SR04 (ultrasonic) — owner: C1

- **Cross-talk**: multiple units firing simultaneously will corrupt each other's readings. Must trigger sequentially — enforced in `firmware/esp32/src/sensors/ultrasonic.h` by design (one sensor serviced per poll cycle), not left to the caller's discipline.
- `pulseIn()` blocks for up to the full timeout (25ms here) if no echo returns — this is why ultrasonic polling runs in its own lower-priority FreeRTOS task, never in the safety task.
- Rated range is typically 2cm–4m; readings below ~2cm are unreliable, not just "close."

## MPU-6050 (IMU) — owner: C3

- Gyro output drifts over time (minutes-scale); accelerometer is noisy but has no long-term drift — this is exactly why a complementary/Kalman filter is used instead of either alone.
- Default I2C address is `0x68`, but shifts to `0x69` if the AD0 pin is pulled high — check this if the MPU-6050 doesn't respond at the expected address on a shared bus with the VL53L1X sensors.
- Needs a settling/warm-up period after power-on before orientation estimates stabilize.

## SIM800L (GSM) — owner: C3

- **Needs up to ~2A current spikes during transmission.** Powering it from a microcontroller's 3.3V/5V logic pin (or a weak USB breadboard supply) will brown it out mid-transmission and reset it. Power from the main battery/buck rail directly, per `docs/WIRING.md`.
- Will not register on the network without an external antenna attached — do not attempt AT commands to check registration before the antenna is connected.
- Logic level is 3.3V-tolerant on most breakouts, but verify the specific board — some require a level shifter for the RX line if driven from a 5V logic source.

## NEO-6M (GPS) — owner: C3

- Will not get a satellite fix indoors — test this expectation outdoors, early, not on demo day.
- Time-to-first-fix (TTFF) can be 30s-a few minutes cold start; don't assume an instant fix in the state machine or test timing.
- Needs its own active antenna (SMA) — a missing or disconnected antenna is the most common "GPS just doesn't work" cause.

## IRF520 MOSFET module — owner: M2

- Logic-level gate threshold matters: confirm the specific module variant is driven correctly from 3.3V GPIO (some IRF520 modules are designed for 5V logic and switch sluggishly or incompletely at 3.3V — may need a gate-level driver stage or a logic-level MOSFET substitute).
- **Flyback diode across the solenoid is mandatory** — an inductive load without one will generate a voltage spike on switch-off that can destroy the MOSFET. Confirm the module has one built in, or add one.

## Solenoids (push-pull, 12V) — owner: M2

- **Duty cycle**: continuous energization overheats the coil. `firmware/esp32/src/actuators/brake.h` enforces a hard `BRAKE_MAX_CONTINUOUS_ON_MS` cutoff independent of hazard logic for exactly this reason — do not remove or bypass it without a documented reason.
- Pull-in force (needed to start moving) is higher than holding force — verify the mechanical linkage doesn't need more than the solenoid's rated pull-in force to engage the wheel lock.

## TP4056 (Li-ion charge/protection) — owner: M2

- Provides charge protection but check whether the specific module variant also includes discharge (over-discharge / short-circuit) protection — some cheap boards are charge-only.
- Never bypass it to "wire the battery directly" for a quick test — Li-ion cells with no protection are a real fire risk, not a theoretical one.

## Raspberry Pi 4 — owner: C2

- Thermal-throttles under sustained CV/OCR load without adequate cooling — confirmed via a 10-minute continuous-inference test (C1v deliverable), not assumed.
- 5V rail is not overvoltage-tolerant — see the power-chain warning in `docs/WIRING.md` about verifying the buck converter's actual trimmed output before connecting.

## Piezoelectric grip sensors — owner: C1

- Output is a voltage proportional to applied pressure/deformation, not a clean digital signal — needs an ADC threshold tuned from real bench data (`GRIP_PRESENT_ADC_THRESHOLD` in `config.h`), not a guessed value.
