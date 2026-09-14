// Pure hazard-classification logic — no hardware I/O, no Arduino.h
// dependency, so this header can be unit tested on the host machine via
// `pio test -e native` (see firmware/esp32/test_native/) without an ESP32
// or any sensor attached. Hardware-facing code (sensors/, actuators/)
// calls into these functions rather than duplicating the thresholds.
#pragma once

#include <cstdint>

#include "config.h"

namespace sensewalk::safety {

// B2: "false positives from a single noisy reading must be filtered out (a
// simple moving-average or 'confirm-twice' rule is enough at this level)."
// Call observe() once per new reading; treat isConfirmed() as the debounced
// hazard signal instead of acting on a single raw reading.
class ConfirmTwice {
public:
    explicit ConfirmTwice(uint8_t requiredConsecutive = GROUND_DROPOFF_CONFIRM_READINGS)
        : required_(requiredConsecutive) {}

    void observe(bool triggered) {
        if (triggered) {
            if (count_ < 255) count_++;
        } else {
            count_ = 0;
        }
    }

    bool isConfirmed() const { return count_ >= required_; }

    void reset() { count_ = 0; }

private:
    uint8_t required_;
    uint8_t count_ = 0;
};

// A "no target" ToF reading (out of range / timeout) is conventionally
// reported as 65535 by VL53L1X libraries — never treat it as a valid
// distance, and never let it be misread as a drop-off.
constexpr uint16_t TOF_NO_TARGET = 0xFFFF;

inline bool isValidToFReading(uint16_t distanceMm) {
    return distanceMm != TOF_NO_TARGET;
}

inline bool isGroundDropoff(uint16_t currentMm, uint16_t baselineMm) {
    if (!isValidToFReading(currentMm) || !isValidToFReading(baselineMm)) return false;
    if (currentMm <= baselineMm) return false;
    return (currentMm - baselineMm) > GROUND_DROPOFF_THRESHOLD_MM;
}

inline bool isForwardObstacleClose(uint16_t distanceMm) {
    return isValidToFReading(distanceMm) && distanceMm < TOF_FWD_HAZARD_MM;
}

inline bool isUltrasonicClose(uint16_t distanceCm) {
    // 0 conventionally means "no echo received" (timeout) for the
    // trigger/echo timing used in sensors/ultrasonic.cpp — not a real
    // zero-distance reading, so never treat it as a hazard.
    return distanceCm != 0 && distanceCm < US_HAZARD_CM;
}

inline bool isGripPresent(int rawAdcValue) {
    return rawAdcValue >= GRIP_PRESENT_ADC_THRESHOLD;
}

// D2: fall pre-check — a brief free-fall-like dip followed by a sharp
// impact spike and a large orientation change, all within one window.
// This mirrors the *shape* of the roadmap's rule; the full multi-sample
// windowing lives in sensors/imu.cpp (which needs real timestamps and a
// ring buffer) — this function takes the three already-extracted features
// so the classification logic itself stays host-testable.
struct FallFeatures {
    uint16_t minAccelMilliG;      // minimum |acceleration| seen in the window (dip)
    uint16_t maxAccelMilliG;      // maximum |acceleration| seen in the window (impact)
    uint16_t orientationDeltaCentideg;  // change in pitch+roll magnitude across the window
};

inline bool isFallDetected(const FallFeatures& f) {
    const bool hadFreefallDip = f.minAccelMilliG < FALL_FREEFALL_ACCEL_MILLIG;
    const bool hadImpactSpike = f.maxAccelMilliG > FALL_IMPACT_ACCEL_MILLIG;
    const bool hadOrientationChange = f.orientationDeltaCentideg > FALL_ORIENTATION_DELTA_CENTIDEG;
    return hadFreefallDip && hadImpactSpike && hadOrientationChange;
}

}  // namespace sensewalk::safety
