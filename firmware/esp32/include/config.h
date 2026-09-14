// SENSEWALK ESP32-S3 firmware — pin assignments and tunable thresholds.
//
// Centralized here (not scattered across .cpp files) so the "gotcha sheet"
// habit from the learning roadmap's S3 module has one obvious place to
// land: when you change a wiring decision, change it here and everyone
// building against this header sees it.
//
// All threshold defaults are STARTING POINTS ONLY — B2/D2 of the learning
// roadmap are explicit that these must be replaced with values derived
// from real bench/field data (50+ logged test walks, 15+ controlled
// drops), not left as guesses. Grep this repo for TODO(calibrate) to find
// every value that needs replacing before Phase 5.

#pragma once

#include <cstdint>

// ---------------------------------------------------------------------------
// Pin assignments
// ---------------------------------------------------------------------------

// I2C bus (shared by both VL53L1X ToF sensors via distinct addresses, and
// the MPU-6050) — ESP32-S3 default I2C pins.
constexpr int PIN_I2C_SDA = 8;
constexpr int PIN_I2C_SCL = 9;

// VL53L1X ToF sensors don't have a fixed alternate I2C address pin-strapped
// on most breakout boards, so each sensor's XSHUT pin is used at boot to
// bring them up one at a time and reassign addresses (see sensors/tof.cpp).
constexpr int PIN_TOF_FWD_XSHUT = 4;   // forward-facing (obstacle) sensor
constexpr int PIN_TOF_GND_XSHUT = 5;   // downward-facing (drop-off) sensor
constexpr uint8_t TOF_FWD_I2C_ADDR = 0x30;
constexpr uint8_t TOF_GND_I2C_ADDR = 0x31;

// HC-SR04 ultrasonic array — 3x, triggered sequentially (never
// simultaneously — see B2's cross-talk warning) on shared trigger timing
// but separate echo pins.
constexpr int PIN_US_L_TRIG = 12;
constexpr int PIN_US_L_ECHO = 13;
constexpr int PIN_US_C_TRIG = 14;
constexpr int PIN_US_C_ECHO = 27;
constexpr int PIN_US_R_TRIG = 26;
constexpr int PIN_US_R_ECHO = 25;

// Piezoelectric grip sensors (analog, threshold-based presence detection).
constexpr int PIN_GRIP_LEFT_ADC = 34;
constexpr int PIN_GRIP_RIGHT_ADC = 35;

// Solenoid brake drivers — one GPIO per channel into an IRF520 MOSFET
// module gate (see docs/BOM.md). LOW-side switching: HIGH = solenoid
// energised = brake engaged.
constexpr int PIN_BRAKE_LEFT = 32;
constexpr int PIN_BRAKE_RIGHT = 33;

// Coin vibration motors (haptic feedback), each via a 2N2222 transistor
// driver stage, PWM-capable pins.
constexpr int PIN_HAPTIC_LEFT = 21;
constexpr int PIN_HAPTIC_RIGHT = 19;

// UART2 to the Raspberry Pi (comms/PROTOCOL.md). Serial (UART0) is left
// free for USB debug logging.
constexpr int PIN_UART_RX2 = 16;
constexpr int PIN_UART_TX2 = 17;

// ---------------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------------

constexpr uint32_t UART_BAUD = 115200;
constexpr uint32_t HEARTBEAT_INTERVAL_MS = 200;
constexpr uint32_t SENSOR_POLL_INTERVAL_MS = 20;   // 50Hz — headroom under the 50ms safety budget
constexpr uint32_t SAFETY_TASK_BUDGET_MS = 50;     // hard requirement from the research report

// Solenoid duty-cycle safety: A2 in the learning roadmap warns solenoids
// overheat if held energised too long. This is a soft cap independent of
// the brake logic — see actuators/brake.cpp.
constexpr uint32_t BRAKE_MAX_CONTINUOUS_ON_MS = 5000;

// ---------------------------------------------------------------------------
// Hazard thresholds — TODO(calibrate) against real bench/field data
// ---------------------------------------------------------------------------

// B2: "a sudden increase in downward-facing ToF distance beyond a
// threshold, sustained for more than one reading, means a drop-off".
constexpr uint16_t GROUND_DROPOFF_THRESHOLD_MM = 150;  // TODO(calibrate)
constexpr uint8_t GROUND_DROPOFF_CONFIRM_READINGS = 2;  // "confirm-twice" noise filter

// Forward ToF / ultrasonic proximity hazard distances.
constexpr uint16_t TOF_FWD_HAZARD_MM = 300;   // TODO(calibrate)
constexpr uint16_t US_HAZARD_CM = 40;         // TODO(calibrate)

// Piezo grip presence — raw ADC threshold above which a hand is considered
// "on the grip". 12-bit ADC (0-4095) on the ESP32.
constexpr int GRIP_PRESENT_ADC_THRESHOLD = 800;  // TODO(calibrate)

// D2 fall detection: free-fall-like dip then impact spike then large
// orientation change, all within this window.
constexpr uint16_t FALL_FREEFALL_ACCEL_MILLIG = 300;   // below this = possible free-fall, TODO(calibrate)
constexpr uint16_t FALL_IMPACT_ACCEL_MILLIG = 2500;    // above this = possible impact, TODO(calibrate)
constexpr uint16_t FALL_ORIENTATION_DELTA_CENTIDEG = 3000;  // 30.00 degrees, TODO(calibrate)
constexpr uint32_t FALL_DETECT_WINDOW_MS = 1000;
