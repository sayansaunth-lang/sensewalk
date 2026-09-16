// Solenoid brake driver (via IRF520 MOSFET modules — see docs/BOM.md).
// Two independent channels (left/right wheel lock).
//
// A2 in the learning roadmap: "solenoids overheat if held energised too
// long" — BRAKE_MAX_CONTINUOUS_ON_MS enforces a hard cutoff independent of
// whatever hazard logic requested the engage, so a stuck sensor reading
// can never cook a solenoid.
#pragma once

#include <Arduino.h>
#include <cstdint>

#include "config.h"

namespace sensewalk::actuators {

class SolenoidBrake {
public:
    void begin() {
        pinMode(PIN_BRAKE_LEFT, OUTPUT);
        pinMode(PIN_BRAKE_RIGHT, OUTPUT);
        digitalWrite(PIN_BRAKE_LEFT, LOW);
        digitalWrite(PIN_BRAKE_RIGHT, LOW);
    }

    void engage() {
        if (!engaged_) {
            engagedAtMs_ = millis();
        }
        engaged_ = true;
        applyOutputs();
    }

    void release() {
        engaged_ = false;
        applyOutputs();
    }

    bool isEngaged() const { return engaged_; }

    // Call every tick from whichever task owns brake state (the hard safety
    // override task). Independently force-releases past the duty-cycle
    // limit regardless of what called engage() — this is the non-negotiable
    // thermal-safety backstop, not a suggestion.
    void enforceDutyCycle() {
        if (engaged_ && (millis() - engagedAtMs_) > BRAKE_MAX_CONTINUOUS_ON_MS) {
            release();
            dutyCycleTripped_ = true;
        }
    }

    bool dutyCycleTripped() const { return dutyCycleTripped_; }
    void clearDutyCycleFlag() { dutyCycleTripped_ = false; }

private:
    void applyOutputs() {
        digitalWrite(PIN_BRAKE_LEFT, engaged_ ? HIGH : LOW);
        digitalWrite(PIN_BRAKE_RIGHT, engaged_ ? HIGH : LOW);
    }

    bool engaged_ = false;
    uint32_t engagedAtMs_ = 0;
    bool dutyCycleTripped_ = false;
};

}  // namespace sensewalk::actuators
