// Piezoelectric handle grip sensing: confirms hand presence before the
// safety layer allows the brake to auto-release (B3 in the learning
// roadmap).
#pragma once

#include <Arduino.h>
#include <cstdint>

#include "config.h"
#include "safety/hazard_rules.h"

namespace sensewalk::sensors {

class GripPair {
public:
    void begin() {
        // ADC pins need no pinMode() on ESP32 (analogRead handles it), but
        // set the attenuation explicitly so the readable voltage range
        // matches the piezo sensor's output rather than relying on the
        // SDK default.
        analogSetPinAttenuation(PIN_GRIP_LEFT_ADC, ADC_11db);
        analogSetPinAttenuation(PIN_GRIP_RIGHT_ADC, ADC_11db);
    }

    void poll() {
        leftRaw_ = analogRead(PIN_GRIP_LEFT_ADC);
        rightRaw_ = analogRead(PIN_GRIP_RIGHT_ADC);
    }

    bool leftPresent() const { return safety::isGripPresent(leftRaw_); }
    bool rightPresent() const { return safety::isGripPresent(rightRaw_); }
    bool anyPresent() const { return leftPresent() || rightPresent(); }

    // Bitmask matching comms/PROTOCOL.md's `grip` tag: bit0=left, bit1=right.
    uint8_t bitmask() const {
        return (leftPresent() ? 0b01 : 0) | (rightPresent() ? 0b10 : 0);
    }

private:
    int leftRaw_ = 0;
    int rightRaw_ = 0;
};

}  // namespace sensewalk::sensors
