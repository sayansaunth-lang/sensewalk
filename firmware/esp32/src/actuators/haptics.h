// Left/right coin vibration motor drivers (via 2N2222 transistor stages),
// independently PWM-controlled (B3 in the learning roadmap). Intensity
// 0-255 matches comms/PROTOCOL.md's `haptic` command encoding.
#pragma once

#include <Arduino.h>
#include <cstdint>

#include "config.h"

namespace sensewalk::actuators {

class Haptics {
public:
    void begin() {
        ledcSetup(kLeftChannel, kPwmFreqHz, kPwmResolutionBits);
        ledcSetup(kRightChannel, kPwmFreqHz, kPwmResolutionBits);
        ledcAttachPin(PIN_HAPTIC_LEFT, kLeftChannel);
        ledcAttachPin(PIN_HAPTIC_RIGHT, kRightChannel);
        setIntensity(0, 0);
    }

    void setIntensity(uint8_t leftIntensity, uint8_t rightIntensity) {
        ledcWrite(kLeftChannel, leftIntensity);
        ledcWrite(kRightChannel, rightIntensity);
        leftIntensity_ = leftIntensity;
        rightIntensity_ = rightIntensity;
    }

    void off() { setIntensity(0, 0); }

    uint8_t leftIntensity() const { return leftIntensity_; }
    uint8_t rightIntensity() const { return rightIntensity_; }

private:
    static constexpr int kLeftChannel = 4;
    static constexpr int kRightChannel = 5;
    static constexpr int kPwmFreqHz = 5000;
    static constexpr int kPwmResolutionBits = 8;  // matches 0-255 intensity range

    uint8_t leftIntensity_ = 0;
    uint8_t rightIntensity_ = 0;
};

}  // namespace sensewalk::actuators
