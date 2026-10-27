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

// Simulated-sensor mode (bench demo with NO sensors attached). Uncomment the
// next line, or build the SIM firmware, to replace only the sensor readings
// with a scripted 40 s scenario (see the sim sensors header). The hazard rules,
// safety override, brake and UART code stay real. NEVER use on a real walker.
// #define SENSEWALK_SIM_SENSORS

// One-sensor build: uncomment to use a single VL53L0X as the forward obstacle sensor
// (no ground drop-off detection). Needs the "VL53L0X" library by Pololu. Do not combine
// with SENSEWALK_SIM_SENSORS.
// #define SENSEWALK_TOF_VL53L0X_FORWARD_ONLY

#include <cstdint>

// ---------------------------------------------------------------------------
// Pin assignments
// ---------------------------------------------------------------------------

// ESP32-S3 pin rules (the first draft used classic-ESP32 pin numbers; GPIO26-35 are
// flash/PSRAM lines on the S3 and driving them crashes the chip, GPIO19/20 are the
// native USB pins, GPIO25 does not exist). Verified by firmware/esp32/test/test_pin_map.
// Avoid: 0 3 45 46 (strapping), 19 20 (USB), 22-25 (absent), 26-37 (flash/PSRAM), 43 44 (UART0).
// Safe to use: 1-18, 21, 38-42, 47, 48.


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
constexpr int PIN_US_C_ECHO = 15;
constexpr int PIN_US_R_TRIG = 38;
constexpr int PIN_US_R_ECHO = 39;

// Piezoelectric grip sensors (analog, threshold-based presence detection).
constexpr int PIN_GRIP_LEFT_ADC = 1;
constexpr int PIN_GRIP_RIGHT_ADC = 2;

// Solenoid brake drivers — one GPIO per channel into an IRF520 MOSFET
// module gate (see docs/BOM.md). LOW-side switching: HIGH = solenoid
// energised = brake engaged.
constexpr int PIN_BRAKE_LEFT = 40;
constexpr int PIN_BRAKE_RIGHT = 41;

// Coin vibration motors (haptic feedback), each via a 2N2222 transistor
// driver stage, PWM-capable pins.
constexpr int PIN_HAPTIC_LEFT = 21;
constexpr int PIN_HAPTIC_RIGHT = 42;

// UART2 to the Raspberry Pi (comms/PROTOCOL.md). Serial (UART0) is left
// free for USB debug logging.
constexpr int PIN_UART_RX2 = 18;  // was 16; moved to 18 to match the wiring (UART1 RX label on the dev board)
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
